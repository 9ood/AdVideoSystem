import base64
import os
import json
import time
from datetime import datetime

import requests

TOKEN_LOG_PATH = os.path.join(os.path.dirname(__file__), 'token_log.json')
RESOURCE_PIC_DIR = os.path.join(os.path.dirname(__file__), 'resource', 'pic')

PRODUCT_IMAGE_MAPPING = {
    '@logo': os.path.join(RESOURCE_PIC_DIR, 'logo.png'),
    '@启动页': os.path.join(RESOURCE_PIC_DIR, '启动页.png'),
    '@玩法页': os.path.join(RESOURCE_PIC_DIR, '玩法页.png'),
    '@练琴页': os.path.join(RESOURCE_PIC_DIR, '练琴页.png'),
    '@选择关卡页': os.path.join(RESOURCE_PIC_DIR, '选择关卡页.png'),
    '@选择关卡页2': os.path.join(RESOURCE_PIC_DIR, '选择关卡页2.png')
}

PRICE_PER_1K_INPUT = 0.0001
PRICE_PER_1K_OUTPUT = 0.0004
DEFAULT_FALLBACK_MODELS = ("qwen/qwen2.5-vl-72b-instruct",)
MAX_RESPONSE_PARSE_RETRIES = 2
DEFAULT_REQUEST_TIMEOUT_SECONDS = 90
DEFAULT_REQUEST_MAX_RETRIES = 2
DEFAULT_REQUEST_RETRY_DELAY_SECONDS = 2


class AIServiceError(RuntimeError):
    pass

def _log_token_usage(model, action, input_tokens, output_tokens):
    total_tokens = input_tokens + output_tokens
    cost = (input_tokens / 1000 * PRICE_PER_1K_INPUT) + (output_tokens / 1000 * PRICE_PER_1K_OUTPUT)

    record = {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model': model,
        'action': action,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': total_tokens,
        'cost_usd': round(cost, 6)
    }

    logs = []
    if os.path.exists(TOKEN_LOG_PATH):
        try:
            with open(TOKEN_LOG_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append(record)

    with open(TOKEN_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def _collect_product_images(seedance_prompt):
    product_images = []
    for ref_name, img_path in PRODUCT_IMAGE_MAPPING.items():
        if ref_name in seedance_prompt and os.path.exists(img_path):
            if img_path not in product_images:
                product_images.append(img_path)
    return product_images

class AIAnalyzer:
    def __init__(self, api_key, model='qwen/qwen3.6-plus', base_url=None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or os.getenv(
            'AI_API_BASE_URL',
            'https://openrouter.ai/api/v1/chat/completions',
        )
        self.request_timeout_seconds = int(
            os.getenv('AI_REQUEST_TIMEOUT_SECONDS', str(DEFAULT_REQUEST_TIMEOUT_SECONDS))
        )
        self.request_max_retries = max(
            1,
            int(os.getenv('AI_REQUEST_MAX_RETRIES', str(DEFAULT_REQUEST_MAX_RETRIES))),
        )
        self.request_retry_delay_seconds = max(
            0,
            int(os.getenv('AI_REQUEST_RETRY_DELAY_SECONDS', str(DEFAULT_REQUEST_RETRY_DELAY_SECONDS))),
        )
        fallback_models = os.getenv('AI_FALLBACK_MODELS')
        if fallback_models is None:
            fallback_models = os.getenv(
                'OPENROUTER_FALLBACK_MODELS',
                ','.join(DEFAULT_FALLBACK_MODELS),
            )
        self.fallback_models = [
            candidate.strip()
            for candidate in fallback_models.split(',')
            if candidate.strip() and candidate.strip() != model
        ]

    def _candidate_models(self):
        seen = set()
        for candidate in [self.model, *self.fallback_models]:
            if candidate not in seen:
                seen.add(candidate)
                yield candidate

    def _build_headers(self):
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def _build_request_payload(self, candidate_model, messages):
        payload = {
            'model': candidate_model,
            'messages': messages,
        }

        # Qwen 3.6 Plus on OpenRouter defaults to long reasoning output, which
        # makes this synchronous video pipeline feel stuck for large scene counts.
        if (
            'openrouter.ai' in self.base_url.lower()
            and candidate_model.startswith('qwen/qwen3.6-plus')
        ):
            payload['reasoning'] = {
                'effort': 'none',
                'exclude': True,
            }

        return payload

    def _extract_error_message(self, response):
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or f"HTTP {response.status_code}"

        error = payload.get('error')
        if isinstance(error, dict):
            return error.get('message') or str(error)
        if error:
            return str(error)
        return response.text.strip() or f"HTTP {response.status_code}"

    def _response_preview(self, response, limit=200):
        text = response.text.strip()
        if not text:
            return "空响应"
        return text[:limit]

    def _build_generate_script_messages(self, scene_description):
        prompt = f"""请根据下面这段镜头描述，判断这个镜头里的人有没有在说话。

如果镜头里的人正在说话，只输出一句自然的中文口播台词，长度控制在 20 到 50 个字。
如果镜头里没有人在说话，或者看起来不像口播镜头，只输出：无台词

硬性要求：
1. 只能输出最终答案
2. 不要解释原因
3. 不要输出标题、序号、Markdown
4. 不要改写成分镜说明

镜头描述：
{scene_description}
"""
        return [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': prompt
                    }
                ]
            }
        ]

    def _normalize_script_output(self, script):
        if not script:
            return ""

        cleaned_lines = [line.strip() for line in script.splitlines() if line.strip()]
        if not cleaned_lines:
            return ""

        first_line = cleaned_lines[0].strip('"\''"“”")
        for prefix in ("台词：", "台词:", "答案：", "答案:", "输出：", "输出:"):
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix):].strip()
                break

        if "无台词" in first_line:
            return ""

        return first_line

    def _request_chat_completion(self, messages, action):
        models_to_try = list(self._candidate_models())
        last_error_message = 'AI 服务调用失败'

        for candidate_model in models_to_try:
            for attempt in range(1, MAX_RESPONSE_PARSE_RETRIES + 1):
                response = None
                for request_attempt in range(1, self.request_max_retries + 1):
                    try:
                        response = requests.post(
                            self.base_url,
                            headers=self._build_headers(),
                            json=self._build_request_payload(candidate_model, messages),
                            timeout=self.request_timeout_seconds,
                        )
                        break
                    except (requests.Timeout, requests.ConnectionError) as exc:
                        last_error_message = (
                            f"{candidate_model} {action} 超时或连接失败，"
                            f"第 {request_attempt} 次尝试，"
                            f"超时设置 {self.request_timeout_seconds} 秒：{str(exc)}"
                        )
                        if request_attempt < self.request_max_retries and self.request_retry_delay_seconds:
                            time.sleep(self.request_retry_delay_seconds)
                        continue
                    except requests.RequestException as exc:
                        raise AIServiceError(f"{action}失败：{str(exc)}") from exc

                if response is None:
                    break

                if response.ok:
                    try:
                        result = response.json()
                    except ValueError:
                        last_error_message = (
                            f"{candidate_model} 返回了无法解析的 JSON，第 {attempt} 次尝试失败。"
                            f"响应开头：{self._response_preview(response)}"
                        )
                        if attempt < MAX_RESPONSE_PARSE_RETRIES:
                            continue
                        break

                    usage = result.get('usage', {})
                    _log_token_usage(
                        candidate_model,
                        action,
                        usage.get('prompt_tokens', 0),
                        usage.get('completion_tokens', 0),
                    )
                    self.model = candidate_model
                    return result['choices'][0]['message']['content'].strip()

                error_message = self._extract_error_message(response)
                last_error_message = error_message
                region_blocked = (
                    response.status_code == 403
                    and 'not available in your region' in error_message.lower()
                )
                if region_blocked:
                    break

                raise AIServiceError(f"{action}失败：{error_message}")

        raise AIServiceError(
            f"{action}失败：已尝试模型 {', '.join(models_to_try)}。最后错误：{last_error_message}"
        )
    
    def encode_image(self, image_path):
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def analyze_frame(self, image_path):
        base64_image = self.encode_image(image_path)
        
        prompt = """请分析这个视频镜头的画面，生成一个适合 Sora AI 视频生成的提示词。

重要要求：
1. 如果画面中有人物，必须描述为中国人（Chinese person/Asian person）
2. 如果有场景，优先使用中国特色场景描述（如：Chinese-style cafe, modern Chinese city, traditional Chinese architecture等）
3. 如果画面中有人在说话（对着镜头、张嘴、手势等），必须加上"speaking in Mandarin Chinese"
4. 详细描述画面中的主要元素（人物、物体、场景）
5. 描述动作和情绪
6. 描述镜头类型（特写、中景、全景等）
7. 描述光线和色调
8. 用英文输出，格式简洁专业

示例格式：
A young Chinese woman in her 20s with long black hair, wearing a white shirt, sitting in a modern Chinese cafe with wooden furniture and warm lighting. She is looking at her phone with a focused expression. Medium shot, natural lighting, warm color tone, cinematic style.

口播场景示例：
A young Chinese man in his 30s speaking in Mandarin Chinese to the camera in a modern office, explaining a product with confident gestures and friendly smile. Medium shot, professional lighting, clean background, corporate style.

请直接输出提示词，不要有其他解释。"""
        
        return self._request_chat_completion(
            [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': prompt
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:image/jpeg;base64,{base64_image}'
                            }
                        }
                    ]
                }
            ],
            '分析镜头画面',
        )
    
    def analyze_global_context(self, first_frame_path, last_frame_path):
        if not first_frame_path or not last_frame_path:
            return {
                'style': 'Cinematic, professional',
                'main_character': 'To be determined',
                'main_scene': 'To be determined'
            }
        
        base64_first = self.encode_image(first_frame_path)
        
        prompt = """请分析这个视频的整体风格和主要元素。

请用以下格式输出（中文）：
风格：[描述整体视觉风格]
主角：[描述主要人物特征]
场景：[描述主要场景环境]

保持简洁，每项不超过50字。"""
        
        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            },
                            {
                                'type': 'image_url',
                                'image_url': {
                                    'url': f'data:image/jpeg;base64,{base64_first}'
                                }
                            }
                        ]
                    }
                ],
                '分析全局信息',
            )
            
            lines = content.split('\n')
            global_info = {
                'style': '',
                'main_character': '',
                'main_scene': ''
            }
            
            for line in lines:
                if '风格' in line or 'style' in line.lower():
                    global_info['style'] = line.split('：')[-1].split(':')[-1].strip()
                elif '主角' in line or 'character' in line.lower():
                    global_info['main_character'] = line.split('：')[-1].split(':')[-1].strip()
                elif '场景' in line or 'scene' in line.lower():
                    global_info['main_scene'] = line.split('：')[-1].split(':')[-1].strip()
            
            return global_info
        except AIServiceError:
            raise
    
    def generate_script(self, image_path, scene_description):
        try:
            script = self._request_chat_completion(
                self._build_generate_script_messages(scene_description),
                '生成镜头台词',
            )
            return self._normalize_script_output(script)
        except AIServiceError:
            raise

    def generate_complete_prompt(self, scene_description, script, duration, shot_type='medium shot'):
        """
        生成完整的 Sora 提示词，包含所有参数、设定和台词
        
        参数:
        - scene_description: 场景描述（来自 analyze_frame）
        - script: 台词脚本（来自 generate_script）
        - duration: 镜头时长（秒）
        - shot_type: 镜头类型（从 scene_description 中提取或默认）
        """
        
        # 从场景描述中提取镜头类型
        shot_types = ['close-up', 'medium shot', 'wide shot', 'full shot', 'extreme close-up']
        detected_shot_type = shot_type
        for st in shot_types:
            if st.lower() in scene_description.lower():
                detected_shot_type = st
                break
        
        # 构建完整的 Sora 提示词
        # 格式参考 Sora 2 官方文档结构
        complete_prompt_parts = []
        
        # 1. 分辨率和时长设置
        resolution = "1920x1080"  # 默认 1080p
        complete_prompt_parts.append(f"[Resolution: {resolution}, Duration: {duration:.1f}s]")
        
        # 2. 场景描述（主体内容）
        complete_prompt_parts.append(scene_description)
        
        # 3. 如果有台词，添加台词信息
        if script:
            complete_prompt_parts.append(f"\n[Audio: Character speaking in Mandarin Chinese - \"{script}\"]")
        
        # 4. 镜头参数
        complete_prompt_parts.append(f"\n[Camera: {detected_shot_type}, smooth movement, professional cinematography]")
        
        # 5. 光线和色调（从场景描述中提取或使用默认值）
        lighting = "natural lighting"
        if "warm lighting" in scene_description.lower():
            lighting = "warm lighting"
        elif "professional lighting" in scene_description.lower():
            lighting = "professional lighting"
        elif "soft lighting" in scene_description.lower():
            lighting = "soft lighting"
        
        color_tone = "cinematic color grading"
        if "warm color tone" in scene_description.lower():
            color_tone = "warm color tone"
        elif "cool color tone" in scene_description.lower():
            color_tone = "cool color tone"
        
        complete_prompt_parts.append(f"[Lighting: {lighting}, {color_tone}]")
        
        # 6. 风格设定
        style = "cinematic style, high quality, 4K"
        if "corporate style" in scene_description.lower():
            style = "corporate style, professional, clean"
        elif "documentary style" in scene_description.lower():
            style = "documentary style, realistic"
        
        complete_prompt_parts.append(f"[Style: {style}]")
        
        # 组合所有部分
        complete_prompt = "\n".join(complete_prompt_parts)
        
        return complete_prompt
    
    def analyze_emotion_and_transform(self, analyzed_scenes):
        """
        识别原视频的核心情绪，并转换成琴童家庭场景
        
        参数:
        - analyzed_scenes: 所有镜头的分析结果列表
        
        返回:
        - dict: {
            'original_emotion': str,  # 原视频的核心情绪
            'transformed_scenario': str,  # 转换后的琴童家庭场景描述
            'emotion_mapping': str  # 情绪映射关系
          }
        """
        
        scenes_details = []
        for i, scene in enumerate(analyzed_scenes):
            scene_info = f"镜头{i+1}: {scene.get('prompt', '')}"
            if scene.get('script'):
                scene_info += f" | 台词: {scene.get('script')}"
            scenes_details.append(scene_info)
        
        scenes_summary = "\n".join(scenes_details)
        
        prompt = f"""你是一个专业的情绪分析和场景转换专家。请分析以下视频的核心情绪，并将其转换成适合"西西魔法钢琴"App的琴童家庭场景。

【西西魔法钢琴App核心信息】
- 产品定位：5-12岁琴童的钢琴学习App
- 核心价值：
  1. 让孩子主动练琴（被动→主动）
  2. 改善亲子陪练关系（紧张→和谐）
  3. 科学进步（痛苦→快乐+成就感）
- 核心功能：游戏化冒险故事、温柔的AI陪练、鼓励式反馈
- 目标用户：琴童家庭（孩子、家长、钢琴老师）

【原视频镜头信息】
{scenes_summary}

请按以下格式输出：

原视频核心情绪: [用1-2个词概括，如：焦虑、快乐、疲惫、紧张、成就感、孤独、兴奋等]

情绪映射关系: [说明如何将原视频情绪转换成琴童家庭场景，例如：
- 如果原视频是"焦虑/压力" → 转换成"陪练紧张/亲子冲突"
- 如果原视频是"快乐/放松" → 转换成"用App后的愉快练琴"
- 如果原视频是"成就感" → 转换成"孩子学会新曲子的喜悦"
- 如果原视频是"孤独/疲惫" → 转换成"传统练琴的枯燥和抗拒"]

琴童家庭场景描述: [用100-150字描述转换后的场景，要求：
1. 必须包含琴童家庭的核心角色（孩子、家长、或钢琴老师）
2. 场景设定：有钢琴的客厅（家庭场景）或琴房（有老师的场景）
3. 暖色调、温暖感
4. 体现情绪对比（被动→主动、痛苦→快乐、紧张→和谐）
5. 自然融入西西魔法钢琴App的使用场景（iPad展示App界面）
6. 孩子穿深圳校服（夏季或冬季）
7. 现代中国家庭的真实感]

请直接输出，不要有其他解释。"""
        
        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '情绪转换分析',
            )
            
            emotion_info = {
                'original_emotion': '',
                'emotion_mapping': '',
                'transformed_scenario': ''
            }
            
            lines = content.split('\n')
            current_field = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if '原视频核心情绪' in line or 'original emotion' in line.lower():
                    emotion_info['original_emotion'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '情绪映射关系' in line or 'emotion mapping' in line.lower():
                    current_field = 'emotion_mapping'
                    mapping_text = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    if mapping_text:
                        emotion_info['emotion_mapping'] = mapping_text
                elif '琴童家庭场景描述' in line or 'transformed scenario' in line.lower():
                    current_field = 'transformed_scenario'
                    scenario_text = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    if scenario_text:
                        emotion_info['transformed_scenario'] = scenario_text
                elif current_field and line:
                    emotion_info[current_field] += ' ' + line
            
            return emotion_info
            
        except AIServiceError:
            raise

    def _parse_creative_core_output(self, content):
        creative_core = {
            'one_sentence': '',
            'ad_type': '',
            'opening_hook': '',
            'storyline': '',
            'conflict': '',
            'product_role': '',
            'app_ui': '',
            'proof_method': '',
            'visual_structure': '',
            'emotion_curve': '',
            'must_preserve': '',
            'replaceable': '',
            'template_risk': '',
            'remake_guidance': '',
            'raw_text': content,
        }
        field_markers = [
            ('一句话创意内核', 'one_sentence'),
            ('广告类型', 'ad_type'),
            ('开头钩子', 'opening_hook'),
            ('故事线', 'storyline'),
            ('核心冲突/看点', 'conflict'),
            ('App在故事里的角色', 'product_role'),
            ('App界面出现方式', 'app_ui'),
            ('证明App有用的方式', 'proof_method'),
            ('关键镜头套路', 'visual_structure'),
            ('情绪变化', 'emotion_curve'),
            ('翻拍必须保留的骨架', 'must_preserve'),
            ('翻拍可以替换的元素', 'replaceable'),
            ('最容易被错误套模板的地方', 'template_risk'),
            ('西西魔法钢琴翻拍建议', 'remake_guidance'),
        ]

        current_field = None
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue

            matched = False
            normalized_line = line.lstrip('0123456789.、)） ')
            for marker, field in field_markers:
                if normalized_line.startswith(marker):
                    current_field = field
                    creative_core[field] = normalized_line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    matched = True
                    break

            if not matched and current_field:
                creative_core[current_field] += ' ' + line

        return creative_core

    def _select_representative_frames(self, frames_info, max_images=12):
        available_frames = [
            frame_info for frame_info in frames_info
            if frame_info.get('keyframe_path') and os.path.exists(frame_info['keyframe_path'])
        ]
        if len(available_frames) <= max_images:
            return available_frames

        selected_indexes = []
        for i in range(max_images):
            index = round(i * (len(available_frames) - 1) / (max_images - 1))
            if index not in selected_indexes:
                selected_indexes.append(index)

        return [available_frames[index] for index in selected_indexes]

    def analyze_creative_core_from_keyframes(self, frames_info):
        """
        直接根据原始关键帧提取原视频创意内核。
        这个步骤必须发生在任何西西魔法钢琴改写之前，避免创意被污染。
        """

        selected_frames = self._select_representative_frames(frames_info)
        if not selected_frames:
            return {
                'one_sentence': '',
                'ad_type': '',
                'opening_hook': '',
                'storyline': '',
                'conflict': '',
                'product_role': '',
                'app_ui': '',
                'proof_method': '',
                'visual_structure': '',
                'emotion_curve': '',
                'must_preserve': '',
                'replaceable': '',
                'template_risk': '',
                'remake_guidance': '',
                'raw_text': '',
            }

        timeline = []
        for index, frame_info in enumerate(selected_frames, start=1):
            timeline.append(
                f"关键帧{index}: {frame_info.get('start_time', 0):.1f}s-"
                f"{frame_info.get('end_time', 0):.1f}s"
            )

        prompt = f"""你是广告创意策略专家。请直接观看这些原始视频关键帧，分析原视频的创意内核。

非常重要：
1. 这是“原视频理解”阶段，不是改编阶段。
2. 除最后一项“西西魔法钢琴翻拍建议”之外，所有字段都只能描述原视频本身。
3. 前13个字段禁止出现“西西魔法钢琴”、禁止出现“练琴改编”、禁止把原视频提前改写成钢琴App广告。
4. 如果原视频是Nike/NRC/跑步/健身/汽车/美妆/餐饮等，请忠实识别原品牌、原场景、原产品角色和原文案结构。
5. 后续翻拍会根据你的“原视频玩法”再做产品替换，所以这里最重要的是别污染原片。

【关键帧时间线】
{chr(10).join(timeline)}

请按以下格式输出，必须具体，不要空话：

一句话创意内核: [只描述原视频，一句话说明这个广告最重要的创意]
广告类型: [如：温情成长 / 伪纪录片 / 产品演示 / 游戏化奇幻 / Vlog挑战 / UGC种草 / 对比证明 / 反转喜剧 / 运动生活方式]
开头钩子: [前3秒用什么抓人]
故事线: [按“开头 -> 发展 -> 转折/证明 -> 结尾”写]
核心冲突/看点: [观众为什么会继续看]
App在故事里的角色: [如果原视频有App，说明它是训练工具、记录工具、证据、笑点来源等；如果没有App，写“无App”]
App界面出现方式: [手机特写、全屏录屏、叠加UI、尾屏等；如果没有App界面，写“无App界面”]
证明App有用的方式: [原视频如何证明产品/服务有效；如果不是App，也要写原产品的证明方式]
关键镜头套路: [时间跳跃、蒙太奇、伪纪录片、拍摄现场、产品界面演示、运动训练混剪等]
情绪变化: [观众/主角从什么感觉到什么感觉]
翻拍必须保留的骨架: [最不能丢的结构，越具体越好]
翻拍可以替换的元素: [人物、场景、道具、曲目、字幕等哪些可以换]
最容易被错误套模板的地方: [如果系统提前套入钢琴App或家庭练琴，会丢掉什么]
西西魔法钢琴翻拍建议: [只在这一项里说明如何保留原玩法，同时自然植入西西魔法钢琴]

请直接输出，不要有其他解释。"""

        content_parts = [{'type': 'text', 'text': prompt}]
        for index, frame_info in enumerate(selected_frames, start=1):
            base64_image = self.encode_image(frame_info['keyframe_path'])
            content_parts.append({
                'type': 'text',
                'text': f"关键帧{index}: {frame_info.get('start_time', 0):.1f}s-"
                        f"{frame_info.get('end_time', 0):.1f}s",
            })
            content_parts.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:image/jpeg;base64,{base64_image}'
                }
            })

        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': content_parts
                    }
                ],
                '根据原始关键帧提取创意内核',
            )

            return self._parse_creative_core_output(content)

        except AIServiceError:
            raise

    def analyze_creative_core(self, analyzed_scenes):
        """
        提取原视频的创意内核，先判断原视频的玩法，再交给后续翻拍脚本使用。
        """

        scenes_details = []
        for i, scene in enumerate(analyzed_scenes):
            scene_info = f"镜头{i+1} ({scene.get('start_time', 0):.1f}s - {scene.get('end_time', 0):.1f}s):\n"
            scene_info += f"  画面描述: {scene.get('prompt', '')}\n"
            if scene.get('script') and scene.get('script') != '无台词':
                scene_info += f"  台词: {scene.get('script')}\n"
            if scene.get('seedance_prompt'):
                scene_info += f"  Seedance提示词: {scene.get('seedance_prompt')}\n"
            scenes_details.append(scene_info)

        scenes_summary = "\n".join(scenes_details)

        prompt = f"""你是一个广告创意策略专家。请只分析原视频的创意内核，不要改编成西西魔法钢琴，不要生成翻拍脚本。

你的任务是先判断：这个广告到底靠什么吸引人？它的玩法是什么？后续翻拍必须保留什么？

【原视频镜头信息】
{scenes_summary}

请按以下格式输出，必须具体，不要空话：

一句话创意内核: [一句话说明这个广告最重要的创意]
广告类型: [如：温情成长 / 伪纪录片 / 产品演示 / 游戏化奇幻 / Vlog挑战 / UGC种草 / 对比证明 / 反转喜剧]
开头钩子: [前3秒用什么抓人]
故事线: [按“开头 -> 发展 -> 转折/证明 -> 结尾”写]
核心冲突/看点: [观众为什么会继续看]
App在故事里的角色: [App是老师、工具、证据、笑点来源、传送门、背景展示等]
App界面出现方式: [iPad特写、手机录屏、背景大屏、叠加UI、尾屏、全屏UI等]
证明App有用的方式: [时间成长、别人反应、前后对比、等级进阶、导演吐槽、即时反馈等]
关键镜头套路: [时间跳跃、练习蒙太奇、伪纪录片、拍摄现场、产品界面演示、游戏化特效、Vlog自拍等]
情绪变化: [观众/主角从什么感觉到什么感觉]
翻拍必须保留的骨架: [最不能丢的结构，越具体越好]
翻拍可以替换的元素: [人物、场景、道具、曲目、字幕等哪些可以换]
最容易被错误套模板的地方: [如果只套“妈妈+孩子+客厅+iPad”，会丢掉什么]
西西魔法钢琴翻拍建议: [如何保留原玩法，同时自然植入西西魔法钢琴]

重要规则：
1. 原视频创意优先，产品植入第二。
2. 不要默认写成“孩子抗拒练琴，妈妈拿出App，孩子开心练琴”。
3. 只有原视频本身就是家庭陪练冲突，才使用普通家庭陪练故事。
4. 如果原视频是伪纪录片、Vlog、产品演示、游戏化奇幻、等级进阶、拍摄现场失控，必须保留这种玩法。
5. 请直接输出，不要有其他解释。"""

        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '提取创意内核',
            )

            return self._parse_creative_core_output(content)

        except AIServiceError:
            raise

    def _build_creative_core_context(self, creative_core):
        if not creative_core:
            return ""

        return f"""
【原视频创意内核 - 最高优先级】
- 一句话创意内核: {creative_core.get('one_sentence', '')}
- 广告类型: {creative_core.get('ad_type', '')}
- 开头钩子: {creative_core.get('opening_hook', '')}
- 故事线: {creative_core.get('storyline', '')}
- 核心冲突/看点: {creative_core.get('conflict', '')}
- App在故事里的角色: {creative_core.get('product_role', '')}
- App界面出现方式: {creative_core.get('app_ui', '')}
- 证明App有用的方式: {creative_core.get('proof_method', '')}
- 关键镜头套路: {creative_core.get('visual_structure', '')}
- 情绪变化: {creative_core.get('emotion_curve', '')}
- 翻拍必须保留的骨架: {creative_core.get('must_preserve', '')}
- 翻拍可以替换的元素: {creative_core.get('replaceable', '')}
- 最容易被错误套模板的地方: {creative_core.get('template_risk', '')}
- 西西魔法钢琴翻拍建议: {creative_core.get('remake_guidance', '')}

硬规则：
1. 必须先保留原视频玩法，再植入西西魔法钢琴。
2. 禁止默认套“妈妈+孩子+客厅+iPad”的普通家庭故事。
3. 如果原视频是伪纪录片、Vlog、产品演示、游戏化奇幻、等级进阶、拍摄现场失控，必须保留这种广告形式。
4. 西西魔法钢琴可以替换原App，但不能吃掉原视频的创意结构。
"""
    
    def generate_condensed_script(self, analyzed_scenes, keyframe_paths, emotion_context=None, creative_core=None):
        """
        生成浓缩脚本（10-15秒版本）
        
        参数:
        - analyzed_scenes: 所有镜头的分析结果列表
        - keyframe_paths: 关键帧图片路径列表（用于AI分析）
        - emotion_context: 情绪识别和场景转换结果（可选）
        """
        
        # 收集所有镜头的完整信息
        total_duration = sum([scene.get('duration', 0) for scene in analyzed_scenes])
        
        # 构建详细的镜头信息，包含画面、台词、时长等所有信息
        scenes_details = []
        for i, scene in enumerate(analyzed_scenes):
            scene_info = f"镜头{i+1} ({scene.get('start_time', 0):.1f}s - {scene.get('end_time', 0):.1f}s):\n"
            scene_info += f"  画面描述: {scene.get('prompt', '')}\n"
            if scene.get('script') and scene.get('script') != '无台词':
                scene_info += f"  台词: {scene.get('script')}\n"
            scenes_details.append(scene_info)
        
        scenes_summary = "\n".join(scenes_details)
        
        # 构建情绪转换上下文
        emotion_context_text = ""
        if emotion_context:
            emotion_context_text = f"""
【情绪转换指导】
- 原视频核心情绪: {emotion_context.get('original_emotion', '未识别')}
- 情绪映射关系: {emotion_context.get('emotion_mapping', '未提供')}
- 琴童家庭场景描述: {emotion_context.get('transformed_scenario', '未提供')}

请严格按照以上场景描述，将原视频转换成琴童家庭场景！
"""
        
        creative_core_context = self._build_creative_core_context(creative_core)

        prompt = f"""你是一个专业的视频导演和编剧，精通Seedance 2.0提示词规范。现在有一个{total_duration:.1f}秒的视频，包含{len(analyzed_scenes)}个镜头。你的任务是：把这个视频改编成一个10-15秒的西西魔法钢琴广告。

【核心任务】
1. 最大化保留原视频的创意玩法、故事结构和镜头套路
2. 将原App或原产品自然替换成"西西魔法钢琴"App
3. 生成符合Seedance 2.0规范的中文提示词
4. 不要默认套用固定家庭练琴模板，除非原视频本身就是这种结构

{creative_core_context}

{emotion_context_text}

【西西魔法钢琴App核心信息】
- 产品定位：5-12岁琴童的钢琴学习App
- 核心价值：让孩子主动练琴（被动→主动）、改善亲子关系（紧张→和谐）、科学进步（痛苦→快乐）
- 核心功能：游戏化冒险故事、温柔的AI陪练、鼓励式反馈
- 可用产品图片：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

【Seedance 2.0 八维度公式 - 必须全部包含】
1. 【主体】年龄+性别+发型+服装（服装必须服从原视频创意，不要默认深圳校服）+配饰+体态
2. 【动作】至少3-5个连贯动作+表情变化+台词（用引号标注）
3. 【场景】有钢琴的客厅或琴房+家具材质颜色+装饰物+空间布局
4. 【风格】治愈系、温馨家庭风等具体风格
5. 【情绪】整体氛围+情感变化（被动→主动、痛苦→快乐、紧张→和谐）
6. 【光影】光线来源+方向+强度+色温（暖色调）
7. 【运镜】镜头运动+景别变化
8. 【细节】材质+颜色+声音等

原视频所有镜头的完整信息:
{scenes_summary}

请按以下格式输出:

核心故事: [用1-2句话概括转换后的琴童家庭故事]

中文提示词(Seedance 2.0): [用中文写一个完整的、可以直接复制粘贴使用的Seedance 2.0提示词。

【强制要求 - 必须全部包含，缺一不可】
1. 【主体】必须写清楚人物年龄、身份、发型、服装；服装要服从原视频玩法（如Vlog日常服、演出服、片场导演服、奇幻游戏风服装），不要默认深圳校服
2. 【动作】必须写至少3-5个连贯动作，例如：坐在钢琴前+看着横屏iPad屏幕显示@练琴页+手指触碰琴键+说"XXX"+表情从XX到XX
3. 【场景】必须写：在XXX，有钢琴或键盘+横屏iPad/产品界面+符合原视频玩法的场景布局（家庭、片场、舞台、Vlog房间、奇幻空间、产品演示棚等）
4. 【风格】必须写：治愈系、温馨家庭风等具体风格
5. 【情绪】必须写：原视频对应的情感变化（如焦虑→自信、怀疑→惊喜、平静→失控、枯燥→沉浸、普通→高光）
6. 【光影】必须写：温暖的光线（暖色调）+光线来源+方向+强度
7. 【运镜】必须写：镜头从XXX到XXX
8. 【细节】必须写：材质+颜色+声音（如琴键声、App的鼓励音效）
9. 如果有台词，用引号标注，自然融入描述中
10. 如果需要展示App界面，使用@符号引用（如@启动页、@练琴页等），设备必须是横屏iPad，不允许出现手机
11. 写成一段流畅完整的话，200-300字
12. 必须体现西西魔法钢琴App，但广告形式必须服从原视频创意内核；可以是Vlog、伪纪录片、产品演示、奇幻游戏化、等级进阶、家庭场景等
13. 产品名必须写"西西魔法钢琴"，不能写错字
14. 如果原视频不是家长引导结构，不要强行写成家长发现和引导App]

例子（仅供参考格式）:
核心故事: 一位琴童从抗拒练琴到通过西西魔法钢琴App主动练琴的转变

中文提示词(Seedance 2.0): 一个中国孩子背着书包冲进家门，兴奋地把书包甩到沙发上，直奔客厅里的钢琴，横屏iPad放在琴谱架上显示@玩法页，屏幕上的西西魔法钢琴弹出星星奖励，孩子按下琴键后，客厅灯光变暗，五线谱和发光音符从iPad里飞出，像游戏关卡一样围绕钢琴旋转，孩子跟着节奏弹奏，表情从好奇变成沉浸和兴奋，镜头从跟拍冲刺切到钢琴侧面中景，再推近到孩子惊喜的面部特写，整体是游戏化奇幻广告风格，保留“主动冲去练琴+现实变成游戏世界”的原视频玩法，背景有轻快琴键声、App鼓励音效和星星通关声，最后出现西西魔法钢琴Logo和下载提示
"""
        
        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '生成浓缩脚本',
            )
            
            condensed_info = {
                'duration': '10-15秒',
                'core_story': '',
                'key_scene_1': '',
                'key_scene_2': '',
                'key_scene_3': '',
                'complete_prompt': ''
            }
            
            lines = content.split('\n')
            current_field = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if '核心故事' in line or 'core story' in line.lower():
                    condensed_info['core_story'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '关键画面1' in line or 'key scene 1' in line.lower():
                    condensed_info['key_scene_1'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '关键画面2' in line or 'key scene 2' in line.lower():
                    condensed_info['key_scene_2'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '关键画面3' in line or 'key scene 3' in line.lower():
                    condensed_info['key_scene_3'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '完整提示词' in line or 'complete prompt' in line.lower():
                    current_field = 'complete_prompt'
                    prompt_text = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    if prompt_text:
                        condensed_info['complete_prompt'] = prompt_text
                elif current_field == 'complete_prompt' and line:
                    condensed_info['complete_prompt'] += ' ' + line
            
            # 如果完整提示词为空，用关键画面组合生成
            if not condensed_info['complete_prompt']:
                condensed_info['complete_prompt'] = f"{condensed_info['key_scene_1']} {condensed_info['key_scene_2']} {condensed_info['key_scene_3']}"
            
            return condensed_info
            
        except AIServiceError:
            raise
    
    def generate_seedance_prompt_for_scene(self, scene_description, script, first_frame_path, last_frame_path, scene_number):
        """
        生成单个镜头的 Seedance 2.0 中文提示词（带 @ 引用首尾帧和产品图片）
        
        参数:
        - scene_description: 英文场景描述
        - script: 中文台词
        - first_frame_path: 首帧图片路径
        - last_frame_path: 尾帧图片路径
        - scene_number: 镜头编号
        
        返回:
        - dict: {'seedance_prompt': str, 'product_images': list}
        """
        
        prompt = f"""你是一个专业的 Seedance 2.0 提示词生成专家。请根据以下信息，生成一个符合 Seedance 2.0 规范的中文提示词。

Seedance 2.0 核心规则：
1. @ 语法：用 @ 符号标注素材用途，格式为 "@素材名 作为XX参考"
2. 8维度公式：主体 + 动作 + 场景 + 风格 + 情绪 + 光影 + 运镜 + 细节
3. 必须使用中文描述
4. 如果涉及产品"西西魔法钢琴"（钢琴学习App），可以自然提及，也可以说"这个App"、"用了它"等
5. 如果需要展示App界面，使用@符号引用图片，可用的图片有：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

当前镜头信息：
- 镜头编号：{scene_number}
- 英文场景描述：{scene_description}
- 中文台词：{script if script else '无台词'}
- 首帧图片：镜头{scene_number}_开始.jpg
- 尾帧图片：镜头{scene_number}_结束.jpg

请按8维度公式生成提示词，要求：
1. 主体：详细描述人物特征（年龄、性别、穿着、发型等），必须是现代中国人
2. 动作：描述人物的连贯动作序列和表情变化
3. 场景：描述环境、背景、道具
4. 风格：描述画面风格（如：电影感、治愈风、商务风等）
5. 情绪：描述整体氛围和情感
6. 光影：描述光线来源、方向、强度、色温
7. 运镜：描述镜头运动
8. 细节：补充关键细节
9. 如果有台词，要在动作部分提及"说着..."
10. 如果场景涉及产品展示，只能使用横屏iPad（不允许手机），可以适当提及"西西魔法钢琴"或"这个App"，并使用 @ 引用产品图片（如 @启动页）
11. 整个提示词要流畅自然，写成一段完整的话，200-300字

示例：
@镜头1_开始.jpg 作为场景参考，@镜头1_结束.jpg 作为动作参考，一位25岁左右的中国女性，留着黑色长发，穿着白色衬衫，坐在现代化的咖啡厅里，微笑着看向镜头说着"今天给大家分享一个好消息"，她轻点手中的iPad，屏幕上显示@启动页，温暖的木质家具和柔和的灯光环绕，午后阳光从窗户洒进来，镜头从中景缓缓推进，电影感风格，轻松愉悦的氛围

请直接输出提示词，不要有其他解释。"""
        
        try:
            seedance_prompt = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '生成镜头Seedance提示词',
            )
            
            # 提取产品图片引用
            return {
                'seedance_prompt': seedance_prompt,
                'product_images': _collect_product_images(seedance_prompt)
            }
            
        except AIServiceError:
            raise
    
    def generate_two_part_script(self, analyzed_scenes, keyframe_paths, emotion_context=None, creative_core=None):
        """
        生成两段式脚本（上集10秒 + 下集10秒）
        
        参数:
        - analyzed_scenes: 所有镜头的分析结果列表
        - keyframe_paths: 关键帧图片路径列表
        - emotion_context: 情绪识别和场景转换结果（可选）
        """
        
        total_duration = sum([scene.get('duration', 0) for scene in analyzed_scenes])
        
        scenes_details = []
        for i, scene in enumerate(analyzed_scenes):
            scene_info = f"镜头{i+1} ({scene.get('start_time', 0):.1f}s - {scene.get('end_time', 0):.1f}s):\n"
            scene_info += f"  画面描述: {scene.get('prompt', '')}\n"
            if scene.get('script') and scene.get('script') != '无台词':
                scene_info += f"  台词: {scene.get('script')}\n"
            if scene.get('seedance_prompt'):
                scene_info += f"  Seedance提示词: {scene.get('seedance_prompt')}\n"
            scenes_details.append(scene_info)
        
        scenes_summary = "\n".join(scenes_details)
        
        # 构建情绪转换上下文
        emotion_context_text = ""
        if emotion_context:
            emotion_context_text = f"""
【情绪转换指导】
- 原视频核心情绪: {emotion_context.get('original_emotion', '未识别')}
- 情绪映射关系: {emotion_context.get('emotion_mapping', '未提供')}
- 琴童家庭场景描述: {emotion_context.get('transformed_scenario', '未提供')}

请严格按照以上场景描述，将原视频转换成琴童家庭场景！
"""
        
        creative_core_context = self._build_creative_core_context(creative_core)

        prompt = f"""你是一个专业的视频导演和编剧，精通Seedance 2.0提示词规范。现在有一个{total_duration:.1f}秒的视频，包含{len(analyzed_scenes)}个镜头。你的任务是：把这个视频拆分成上下两集，每集10秒，总共20秒，改编成西西魔法钢琴广告。

【核心任务】
1. 最大化保留原视频的创意玩法、故事结构和镜头套路
2. 将原App或原产品自然替换成"西西魔法钢琴"App
3. 生成符合Seedance 2.0规范的中文提示词
4. 上集和下集的分工必须服从原视频创意：可以是问题→解决，也可以是挑战→进步、片场失控→反向证明、产品演示→下载转化、游戏化体验→回到现实等

{creative_core_context}

{emotion_context_text}

【西西魔法钢琴App核心信息】
- 产品定位：5-12岁琴童的钢琴学习App
- 核心价值：让孩子主动练琴（被动→主动）、改善亲子关系（紧张→和谐）、科学进步（痛苦→快乐）
- 核心功能：游戏化冒险故事、温柔的AI陪练、鼓励式反馈
- 可用产品图片：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

【严格要求 - 必须100%遵守】
1. 这不是简单的时间切分，而是要保留原视频的广告玩法：问题场景 → 发现/出现解决工具（西西魔法钢琴） → 解决方案场景，只是其中一种可选结构，不是默认模板
2. 上集和下集要保持视觉一致性（孩子、家长、场景、风格、光线等）
3. 用户会用上集的最后一帧作为下集的首帧，所以两集要能自然衔接
4. 上集必须承担原视频前半段的创意任务，例如开头钩子、挑战设定、片场设定、产品界面展示或问题出现
5. 下集必须承担原视频后半段的创意任务，例如进步证明、反转笑点、等级升级、成功表演、真实演示或下载转化
6. 主要人物可以改成中国人，但年龄、服装、身份要服从原视频玩法；不要默认深圳校服
7. 场景必须有钢琴或键盘，但可以根据原视频玩法选择家庭客厅、Vlog房间、拍摄片场、舞台、产品演示棚、奇幻游戏空间等
8. 必须体现原视频的情绪转换；如果原视频不是亲子冲突，就不要强行写成被动→主动、紧张→和谐
9. 如果需要展示App界面，只能使用横屏iPad（不允许手机），使用@符号引用图片，可用的图片有：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2
10. 产品名必须写"西西魔法钢琴"，不能写错字
11. 如果原视频不是家长引导结构，不要强行写成家长发现和引导App

【Seedance 2.0 八维度公式 - 每个维度都必须详细描述，不能省略】
1. 【主体】必须包含：人物年龄+性别+发型+符合原视频玩法的服装+配饰+体态；如果原视频没有家长，不要强行添加家长
2. 【动作】必须包含：至少3-5个连贯动作、表情变化、肢体语言、如有台词用引号标注
3. 【场景】必须包含：有钢琴的客厅或琴房+家具材质和颜色+装饰物+道具+空间布局（暖色调）
4. 【风格】必须明确：治愈系、温馨家庭风等具体风格
5. 【情绪】必须描述：整体氛围、情感基调、情绪变化（被动→主动、痛苦→快乐、紧张→和谐）
6. 【光影】必须包含：光线来源（如窗户、灯光）、方向、强度、色温（暖色调）
7. 【运镜】必须描述：镜头运动方式（推拉摇移跟、固定、升降等）、景别变化（远景/全景/中景/近景/特写）
8. 【细节】必须补充：材质、颜色、纹理、声音（如琴键声、App的鼓励音效）、环境音等

【禁止的错误示例】
❌ "一位孩子" → 太笼统，必须写"一位8岁的中国女孩，齐肩黑色直发，穿着深圳夏季校服（白色短袖衬衫配深蓝色短裙）"
❌ "坐在钢琴前" → 太简单，必须写"坐在黑色立式钢琴前的棕色琴凳上，iPad放在琴谱架上显示@练琴页"
❌ "光线很好" → 太模糊，必须写"温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，整体色调温馨明亮偏暖"
❌ "镜头推进" → 太简略，必须写"镜头从中景缓缓推进到孩子面部特写"
❌ "现代风格" → 太笼统，必须写"治愈系温馨家庭风，米色墙面配浅木色家具"

原视频所有镜头的完整信息（包含详细的Seedance提示词作为参考）:
{scenes_summary}

请按以下格式输出:

核心故事: [用1-2句话概括整个视频讲了什么故事]

上集提示词（前半段场景）: [用中文写一个完整的、可以直接复制粘贴使用的Seedance 2.0提示词。

【强制要求 - 必须全部包含，缺一不可】
1. 【主体】必须写清楚人物年龄、身份、发型、服装；服装和身份要服从原视频玩法（如Vlog女孩、片场导演、演出孩子、游戏化练琴孩子、产品演示者等）
2. 【动作】必须写至少3-5个连贯动作，动作要对应原视频前半段玩法，例如：冲进家门+打开App+触发星星奖励，或直视镜头说明挑战+第一次练习，或导演打断拍摄+演员继续弹得太好
3. 【场景】必须写：在XXX，有钢琴或键盘+横屏iPad/产品界面+符合原视频玩法的空间布局（家庭、Vlog房间、片场、舞台、产品演示棚、奇幻空间等）
4. 【风格】必须写：治愈系、温馨家庭风等具体风格
5. 【情绪】必须写：前半段的氛围，要服从原视频（如焦虑、好奇、兴奋、怀疑、片场尴尬、游戏化惊喜等）
6. 【光影】必须写：温暖的光线（暖色调）+光线来源+方向+强度（如温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，整体色调温馨明亮偏暖）
7. 【运镜】必须写：镜头从XXX到XXX（如从全景缓缓推进到孩子面部特写）
8. 【细节】必须写：材质、颜色、声音等（如米色墙面、浅木色家具、琴键声断断续续、环境音压抑）
9. 如果有台词，用引号标注，自然融入描述中
10. 写成一段流畅完整的话，300-400字
11. 必须体现西西魔法钢琴与钢琴/键盘的关系
12. 必须体现原视频前半段的开头钩子和玩法，不要强行改成被动、痛苦、紧张]

下集提示词（后半段场景）: [用中文写一个完整的、可以直接复制粘贴使用的Seedance 2.0提示词。

【强制要求 - 必须全部包含，缺一不可】
1. 【开头】必须写：@上集尾帧，（注意：@上集尾帧必须在最开头）
2. 【主体】必须写：同一位主要人物，发型、服装、身份与上集一致；如果原视频需要新角色（导演、观众、家人、工作人员），也要保持前后逻辑一致
3. 【动作】必须写至少3-5个连贯动作，动作要对应原视频后半段玩法，例如：升级练习+成功表演+观众反应，或导演崩溃+片场失控，或UI全屏展示+下载转化，或游戏化世界达到高潮
4. 【场景】必须写：同一套或逻辑连续的场景布局；如果原视频后半段有舞台、片场、尾屏、奇幻空间，要保留
5. 【风格】必须写：治愈系、温馨家庭风等具体风格（必须与上集一致）
6. 【情绪】必须写：从XXX到XXX的情感转变，必须服从原视频（如焦虑到自信、普通到惊艳、怀疑到信服、平静到失控、现实到奇幻沉浸）
7. 【光影】必须写：同样的温暖光线（暖色调）（必须与上集完全一致，如温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，温馨明亮偏暖的色调）
8. 【运镜】必须写：镜头从XXX到XXX（如从侧面中景缓缓推进到孩子和家长的面部特写）
9. 【细节】必须写：材质、颜色、声音等（如米色墙面、浅木色家具、琴键声流畅、App的鼓励音效、欢快的旋律声）
10. 如果有台词，用引号标注，自然融入描述中
11. 如果需要展示App界面，使用@符号引用（如@玩法页、@练琴页等）
12. 写成一段流畅完整的话，300-400字
13. 必须体现西西魔法钢琴App和钢琴/键盘
14. 必须体现原视频后半段的证明方式或转化方式
15. 确保人物、场景、光线与上集逻辑连续，只有动作、情绪和证明结果在发展]

例子（仅供参考格式，注意详细程度）:
核心故事: 一个孩子通过西西魔法钢琴App把练琴变成游戏闯关体验，从放学冲回家到沉浸在奇幻音乐世界里，证明练琴也可以像玩游戏一样主动上头

上集提示词（前半段场景）: 一位9岁的中国男孩，短发，穿着蓝色连帽卫衣和运动裤，背着书包冲进家门，兴奋地把书包甩到沙发上，直奔客厅里的电钢琴，横屏iPad放在琴谱架上显示@玩法页，屏幕上的西西魔法钢琴出现“开始练琴”和星星奖励，男孩坐下后快速按下第一个琴键，眼睛发亮地说"今天我要闯到下一关"，客厅里有木质地板、浅色沙发和暖色台灯，镜头从门口跟拍冲刺动作，切到钢琴侧面中景，再推近到iPad和手指特写，整体是轻快、游戏化、带悬念的广告风格，背景有急促脚步声、书包落下声、清脆琴键声和App奖励音效

下集提示词（后半段场景）: @上集尾帧，同一位9岁的中国男孩，短发，穿着蓝色连帽卫衣和运动裤，坐在同一台电钢琴前，横屏iPad继续显示@练琴页，男孩按下琴键后，客厅墙面和地板逐渐变成紫色奇幻空间，发光五线谱从iPad里飞出，彩色音符和星星奖励像游戏关卡一样环绕钢琴旋转，男孩跟着节奏连续弹奏，表情从惊讶变成沉浸和兴奋，最后屏幕跳出“本关完成”的奖励画面，他回到现实客厅，睁大眼睛笑着说"原来练琴也能这么好玩"，镜头从环绕运镜切到孩子面部特写，再切到西西魔法钢琴Logo和下载提示，背景有流畅琴键声、魔法音效、星星通关声和轻快音乐

请直接输出，不要有其他解释。"""
        
        try:
            content = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '生成两段式脚本',
            )
            
            two_part_info = {
                'core_story': '',
                'part1_content': '',
                'part2_content': '',
                'part1_seedance_prompt': '',
                'part2_seedance_prompt': ''
            }
            
            lines = content.split('\n')
            current_field = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if '核心故事' in line:
                    two_part_info['core_story'] = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                elif '上集提示词' in line:
                    current_field = 'part1_seedance_prompt'
                    prompt_text = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    if prompt_text:
                        two_part_info['part1_seedance_prompt'] = prompt_text
                elif '下集提示词' in line:
                    current_field = 'part2_seedance_prompt'
                    prompt_text = line.split(':', 1)[-1].split('：', 1)[-1].strip()
                    if prompt_text:
                        two_part_info['part2_seedance_prompt'] = prompt_text
                elif current_field and line:
                    two_part_info[current_field] += ' ' + line
            
            two_part_info['part1_product_images'] = _collect_product_images(
                two_part_info.get('part1_seedance_prompt', '')
            )
            two_part_info['part2_product_images'] = _collect_product_images(
                two_part_info.get('part2_seedance_prompt', '')
            )
            
            return two_part_info
            
        except AIServiceError:
            raise
    
    def generate_seedance_prompt_for_condensed(self, condensed_script_info, creative_core=None):
        """
        生成浓缩脚本的 Seedance 2.0 中文提示词（可以使用 @ 引用产品图片）
        
        参数:
        - condensed_script_info: 浓缩脚本信息（包含核心故事、关键画面、完整提示词）
        
        返回:
        - dict: {'seedance_prompt': str, 'product_images': list}
        """
        
        core_story = condensed_script_info.get('core_story', '')
        complete_prompt = condensed_script_info.get('complete_prompt', '')
        creative_core_context = self._build_creative_core_context(creative_core)
        
        prompt = f"""你是一个专业的 Seedance 2.0 提示词生成专家。请根据以下浓缩脚本信息，生成一个符合 Seedance 2.0 规范的中文提示词。

{creative_core_context}

Seedance 2.0 核心规则：
1. 8维度公式：[主体] + [动作] + [场景] + [风格] + [情绪] + [光影] + [运镜] + [细节]
2. 必须使用中文描述
3. 如果涉及产品"西西魔法钢琴"（钢琴学习App），可以自然提及，也可以说"这个App"、"用了它"等
4. 如果需要展示App界面，使用@符号引用图片，可用的图片有：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

浓缩脚本信息：
- 核心故事：{core_story}
- 英文完整提示词：{complete_prompt}

请按8维度公式生成一个10-15秒视频的中文提示词：

要求：
0. 必须保留上方“原视频创意内核”的广告玩法；不要把Vlog、伪纪录片、运动生活方式、产品演示、游戏化奇幻等统一改成普通家庭陪练故事
1. 主体：详细描述主要人物特征（年龄、发型、服装、配饰、体态）
2. 动作：描述人物的连贯动作序列和表情变化（至少3-5个动作）
3. 场景：详细描述环境和背景（布局、家具、装饰）
4. 风格：明确画面风格（治愈系、现代都市风等）
5. 情绪：描述整体氛围和情感变化
6. 光影：详细描述光线来源、方向、强度、色温
7. 运镜：描述镜头运动（推拉摇移等）
8. 细节：补充关键细节（材质、颜色、声音等）
9. 如果有台词，用引号标注，自然融入描述中
10. 如果需要展示App界面，使用@符号引用（如@启动页、@练琴页等）
11. 整个提示词要流畅，描述一个完整的10-15秒视频故事
12. 写成一段流畅完整的话，200-300字

示例：
一位28岁的中国女性，齐肩黑色直发，穿着浅灰色毛衣配黑色休闲裤，从兴奋地坐在沙发上看着iPad说"听说这个西西魔法钢琴App特别好用"，她点开@启动页，屏幕显示精美的钢琴界面，然后她起身走向黑色立式钢琴，轻轻触碰琴键低语"原来弹琴是这种感觉"，最后坐在琴凳上跟着@练琴页的指引练习，成功弹奏后露出喜悦的笑容说"我终于学会了"，整个过程在上海现代公寓的温暖午后阳光中展开，柔和自然的光线透过落地窗洒进来，在木地板上形成光影，镜头从中景推进到特写，温馨励志的治愈系风格，记录一段从好奇到成就的成长旅程

请直接输出提示词，不要有其他解释。"""
        
        try:
            seedance_prompt = self._request_chat_completion(
                [
                    {
                        'role': 'user',
                        'content': [
                            {
                                'type': 'text',
                                'text': prompt
                            }
                        ]
                    }
                ],
                '生成浓缩Seedance提示词',
            )
            
            return {
                'seedance_prompt': seedance_prompt,
                'product_images': _collect_product_images(seedance_prompt)
            }
            
        except AIServiceError:
            raise
