import requests
import base64
import os
import json
from datetime import datetime

TOKEN_LOG_PATH = os.path.join(os.path.dirname(__file__), 'token_log.json')

PRICE_PER_1K_INPUT = 0.0001
PRICE_PER_1K_OUTPUT = 0.0004

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

class AIAnalyzer:
    def __init__(self, api_key, model='google/gemini-3-flash-preview'):
        self.api_key = api_key
        self.model = model
        self.base_url = 'https://openrouter.ai/api/v1/chat/completions'
    
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
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
            ]
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '分析镜头画面', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            return f"Error analyzing frame: {str(e)}"
    
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
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
            ]
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '分析全局信息', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            content = result['choices'][0]['message']['content'].strip()
            
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
        except Exception as e:
            return {
                'style': f'Error: {str(e)}',
                'main_character': 'Error analyzing',
                'main_scene': 'Error analyzing'
            }
    
    def generate_script(self, image_path, scene_description):
        base64_image = self.encode_image(image_path)
        
        prompt = f"""请分析这个视频镜头，判断是否是口播场景（有人对着镜头说话）。

如果是口播场景，请根据画面内容和场景描述，生成一段合适的中文台词（20-50字）。
如果不是口播场景，请输出"无台词"。

场景描述：{scene_description}

要求：
1. 台词要自然、口语化
2. 符合画面中人物的身份和场景
3. 如果是产品介绍，要突出产品特点
4. 如果是教学，要清晰易懂
5. 直接输出台词，不要有其他解释

示例：
- 产品介绍："大家好，今天给大家带来一款全新的智能手表，它不仅外观时尚，功能也非常强大。"
- 教学场景："接下来我们来学习如何使用这个工具，首先打开主界面。"
- 日常分享："这家咖啡店的环境真的很棒，特别适合周末来放松一下。"
"""
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
            ]
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '生成台词', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            script = result['choices'][0]['message']['content'].strip()
            return script if script and script != "无台词" else ""
        except Exception as e:
            return ""
    
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
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '情绪转换分析', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            content = result['choices'][0]['message']['content'].strip()
            
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
            
        except Exception as e:
            return {
                'original_emotion': f'Error: {str(e)}',
                'emotion_mapping': 'Error analyzing',
                'transformed_scenario': 'Error analyzing'
            }
    
    def generate_condensed_script(self, analyzed_scenes, keyframe_paths, emotion_context=None):
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
        
        prompt = f"""你是一个专业的视频导演和编剧，精通Seedance 2.0提示词规范。现在有一个{total_duration:.1f}秒的视频，包含{len(analyzed_scenes)}个镜头。你的任务是：把这个视频的故事浓缩成一个10-15秒的琴童家庭场景视频。

【核心任务】
1. 识别原视频的核心情绪和故事
2. 将其转换成适合"西西魔法钢琴"App的琴童家庭场景
3. 生成符合Seedance 2.0规范的中文提示词

{emotion_context_text}

【西西魔法钢琴App核心信息】
- 产品定位：5-12岁琴童的钢琴学习App
- 核心价值：让孩子主动练琴（被动→主动）、改善亲子关系（紧张→和谐）、科学进步（痛苦→快乐）
- 核心功能：游戏化冒险故事、温柔的AI陪练、鼓励式反馈
- 可用产品图片：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

【Seedance 2.0 八维度公式 - 必须全部包含】
1. 【主体】年龄+性别+发型+服装（深圳校服：夏季/冬季）+配饰+体态
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
1. 【主体】必须写：一位XX岁的中国孩子（5-12岁），XXX发型，穿着深圳XX季校服（如深圳夏季校服：白色短袖衬衫配深蓝色短裤/裙子，或深圳冬季校服：深蓝色运动外套配长裤）
2. 【动作】必须写至少3-5个连贯动作，例如：坐在钢琴前+看着横屏iPad屏幕显示@练琴页+手指触碰琴键+说"XXX"+表情从XX到XX
3. 【场景】必须写：在XXX（如深圳现代家庭的客厅），有钢琴+横屏iPad+家长/老师+家具布局（暖色调）
4. 【风格】必须写：治愈系、温馨家庭风等具体风格
5. 【情绪】必须写：情感变化（被动→主动、痛苦→快乐、紧张→和谐）
6. 【光影】必须写：温暖的光线（暖色调）+光线来源+方向+强度
7. 【运镜】必须写：镜头从XXX到XXX
8. 【细节】必须写：材质+颜色+声音（如琴键声、App的鼓励音效）
9. 如果有台词，用引号标注，自然融入描述中
10. 如果需要展示App界面，使用@符号引用（如@启动页、@练琴页等），设备必须是横屏iPad，不允许出现手机
11. 写成一段流畅完整的话，200-300字
12. 必须体现琴童家庭场景（孩子+家长/老师+钢琴+西西魔法钢琴App）
13. 产品名必须写"西西魔法钢琴"，不能写错字
14. 家长必须是发现和引导使用App的角色，不是孩子自己发现]

例子（仅供参考格式）:
核心故事: 一位琴童从抗拒练琴到通过西西魔法钢琴App主动练琴的转变

中文提示词(Seedance 2.0): 一位8岁的中国女孩，齐肩黑色马尾辫，穿着深圳夏季校服（白色短袖衬衫配深蓝色短裙和白色运动鞋），最初坐在深圳现代家庭客厅的黑色立式钢琴前，低着头双手抱胸，妈妈站在旁边焦急地说"快点练琴，马上要考级了"，女孩皱着眉头不情愿地触碰琴键，妈妈拿出横屏iPad打开@启动页，屏幕显示西西魔法钢琴的游戏界面，妈妈温柔地说"宝贝，妈妈发现了一个好玩的App，我们试试看"，女孩眼神一亮，横屏iPad放在琴谱架上显示@练琴页，女孩跟着App的指引开始弹奏，手指在琴键上越来越流畅，App发出鼓励的音效"太棒了！"，女孩露出笑容说"原来练琴可以这么好玩"，妈妈也放松地微笑，温暖的午后阳光透过米色纱帘洒进客厅，在浅色木地板和钢琴表面形成柔和的光影，整体色调温馨明亮偏暖，现代简约的家居风格，米色沙发配浅木色茶几，镜头从全景缓缓推进到女孩和横屏iPad的近景，从紧张抗拒到主动快乐的情感转变，治愈系亲子关系改善的温馨故事，背景有琴键声和App的轻柔音乐
"""
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '生成浓缩脚本', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            content = result['choices'][0]['message']['content'].strip()
            
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
            
        except Exception as e:
            return {
                'duration': '10-15秒',
                'core_story': f'Error: {str(e)}',
                'key_scene_1': 'Error analyzing',
                'key_scene_2': 'Error analyzing',
                'key_scene_3': 'Error analyzing',
                'complete_prompt': 'Error generating prompt'
            }
    
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
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '生成镜头Seedance提示词', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            seedance_prompt = result['choices'][0]['message']['content'].strip()
            
            # 提取产品图片引用
            product_image_mapping = {
                '@logo': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/logo.png',
                '@启动页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/启动页.png',
                '@玩法页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/玩法页.png',
                '@练琴页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/练琴页.png',
                '@选择关卡页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页.png',
                '@选择关卡页2': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页2.png'
            }
            
            product_images = []
            for ref_name, img_path in product_image_mapping.items():
                if ref_name in seedance_prompt and os.path.exists(img_path):
                    if img_path not in product_images:
                        product_images.append(img_path)
            
            return {
                'seedance_prompt': seedance_prompt,
                'product_images': product_images
            }
            
        except Exception as e:
            return {
                'seedance_prompt': f"生成失败: {str(e)}",
                'product_images': []
            }
    
    def generate_two_part_script(self, analyzed_scenes, keyframe_paths, emotion_context=None):
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
        
        prompt = f"""你是一个专业的视频导演和编剧，精通Seedance 2.0提示词规范。现在有一个{total_duration:.1f}秒的视频，包含{len(analyzed_scenes)}个镜头。你的任务是：把这个视频的故事拆分成上下两集，每集10秒，总共20秒，并转换成琴童家庭场景。

【核心任务】
1. 识别原视频的核心情绪和故事
2. 将其转换成适合"西西魔法钢琴"App的琴童家庭场景
3. 生成符合Seedance 2.0规范的中文提示词
4. 上集讲问题场景（如陪练紧张、孩子被动），下集讲解决方案（用App后变和谐、主动）

{emotion_context_text}

【西西魔法钢琴App核心信息】
- 产品定位：5-12岁琴童的钢琴学习App
- 核心价值：让孩子主动练琴（被动→主动）、改善亲子关系（紧张→和谐）、科学进步（痛苦→快乐）
- 核心功能：游戏化冒险故事、温柔的AI陪练、鼓励式反馈
- 可用产品图片：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2

【严格要求 - 必须100%遵守】
1. 这不是简单的时间切分，而是要重新创作三个连贯的琴童家庭场景：问题场景 → 发现/出现解决工具（西西魔法钢琴） → 解决方案场景
2. 上集和下集要保持视觉一致性（孩子、家长、场景、风格、光线等）
3. 用户会用上集的最后一帧作为下集的首帧，所以两集要能自然衔接
4. 上集必须包含：问题场景（如孩子被动练琴、亲子关系紧张、练琴痛苦）+ 家长发现西西魔法钢琴App并引导孩子使用
5. 下集必须包含：使用西西魔法钢琴App后的解决方案场景（孩子主动、关系和谐、练琴快乐）
6. 所有人物必须是中国人，孩子必须穿深圳校服（夏季：白色短袖衬衫配深蓝色短裤/裙子；冬季：深蓝色运动外套配长裤）
7. 场景必须是有钢琴的客厅或琴房，暖色调，温馨家庭氛围
8. 必须体现情绪转换：被动→主动、痛苦→快乐、紧张→和谐
9. 如果需要展示App界面，只能使用横屏iPad（不允许手机），使用@符号引用图片，可用的图片有：@logo、@启动页、@玩法页、@练琴页、@选择关卡页、@选择关卡页2
10. 产品名必须写"西西魔法钢琴"，不能写错字
11. 家长必须是发现和引导使用App的角色，不是孩子自己发现

【Seedance 2.0 八维度公式 - 每个维度都必须详细描述，不能省略】
1. 【主体】必须包含：孩子年龄（5-12岁）+性别+发型+深圳校服（夏季/冬季）+配饰+体态；家长年龄+性别+发型+服装
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

上集提示词（问题场景）: [用中文写一个完整的、可以直接复制粘贴使用的Seedance 2.0提示词。

【强制要求 - 必须全部包含，缺一不可】
1. 【主体】必须写：一位XX岁（5-12岁）的中国孩子，XXX发型，穿着深圳XX季校服（如深圳夏季校服：白色短袖衬衫配深蓝色短裤/裙子，或深圳冬季校服：深蓝色运动外套配长裤）；一位XX岁的家长（妈妈/爸爸），XXX发型，穿着XXX
2. 【动作】必须写至少3-5个连贯动作，例如：孩子坐在钢琴前+低着头+手指僵硬地按琴键+妈妈站在旁边+皱着眉头+说"XXX"+孩子表情痛苦+眼神躲闪+身体紧绷
3. 【场景】必须写：在XXX（如深圳现代家庭的客厅），有钢琴+XXX布局（如米色布艺沙发、浅色木地板、白色纱帘、黑色立式钢琴、暖色调装饰）
4. 【风格】必须写：治愈系、温馨家庭风等具体风格
5. 【情绪】必须写：问题场景的氛围（如紧张、被动、痛苦、压抑）
6. 【光影】必须写：温暖的光线（暖色调）+光线来源+方向+强度（如温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，整体色调温馨明亮偏暖）
7. 【运镜】必须写：镜头从XXX到XXX（如从全景缓缓推进到孩子面部特写）
8. 【细节】必须写：材质、颜色、声音等（如米色墙面、浅木色家具、琴键声断断续续、环境音压抑）
9. 如果有台词，用引号标注，自然融入描述中
10. 写成一段流畅完整的话，300-400字
11. 必须体现琴童家庭场景（孩子+家长+钢琴）
12. 必须体现问题场景（被动、痛苦、紧张）]

下集提示词（解决方案场景）: [用中文写一个完整的、可以直接复制粘贴使用的Seedance 2.0提示词。

【强制要求 - 必须全部包含，缺一不可】
1. 【开头】必须写：@上集尾帧，（注意：@上集尾帧必须在最开头）
2. 【主体】必须写：同一位XX岁（5-12岁）的中国孩子，XXX发型（必须与上集完全一致），穿着深圳XX季校服（必须与上集完全一致）；同一位XX岁的家长（妈妈/爸爸），XXX发型（必须与上集完全一致），穿着XXX（必须与上集完全一致）
3. 【动作】必须写至少3-5个连贯动作，例如：孩子坐在钢琴前+iPad放在琴谱架上显示@练琴页+妈妈坐在旁边+微笑着说"XXX"+孩子眼神专注看屏幕+手指流畅地在琴键上移动+跟着App的节奏+成功弹奏+抬头露出笑容+妈妈竖起大拇指+两人击掌
4. 【场景】必须写：在同一间XXX（如深圳现代家庭的客厅），XXX布局（必须与上集完全一致，如黑色立式钢琴、棕色琴凳、浅色木地板、白色纱帘、暖色调装饰）
5. 【风格】必须写：治愈系、温馨家庭风等具体风格（必须与上集一致）
6. 【情绪】必须写：从XXX到XXX的情感转变（如从紧张到和谐、从被动到主动、从痛苦到快乐）
7. 【光影】必须写：同样的温暖光线（暖色调）（必须与上集完全一致，如温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，温馨明亮偏暖的色调）
8. 【运镜】必须写：镜头从XXX到XXX（如从侧面中景缓缓推进到孩子和家长的面部特写）
9. 【细节】必须写：材质、颜色、声音等（如米色墙面、浅木色家具、琴键声流畅、App的鼓励音效、欢快的旋律声）
10. 如果有台词，用引号标注，自然融入描述中
11. 如果需要展示App界面，使用@符号引用（如@玩法页、@练琴页等）
12. 写成一段流畅完整的话，300-400字
13. 必须体现琴童家庭场景（孩子+家长+钢琴+西西魔法钢琴App）
14. 必须体现解决方案场景（主动、快乐、和谐）
15. 确保人物、场景、光线与上集完全一致，只有动作和情绪在发展]

例子（仅供参考格式，注意详细程度）:
核心故事: 一位琴童通过西西魔法钢琴App从被动练琴到主动快乐学习，亲子关系从紧张到和谐的转变故事

上集提示词（问题场景）: 一位8岁的中国女孩，齐肩黑色直发扎着马尾，穿着深圳夏季校服（白色短袖衬衫配深蓝色短裙和白色运动鞋），坐在深圳现代家庭客厅的黑色立式钢琴前的棕色琴凳上，低着头，眼神躲闪，手指僵硬地按着琴键，琴键声断断续续，一位35岁的妈妈，中长黑色直发，穿着米色休闲衬衫配深蓝色牛仔裤，站在孩子身后，双手抱胸，皱着眉头说"你怎么又弹错了？我说了多少遍了！"，孩子身体紧绷，表情痛苦，眼眶泛红，小声说"我不想练了"，妈妈叹气摇头，客厅里有米色布艺沙发、浅色木地板、白色纱帘、暖色调装饰画，温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，整体色调温馨明亮偏暖，但氛围紧张压抑，治愈系温馨家庭风，镜头从全景缓缓推进到孩子痛苦的面部特写，背景有断断续续的琴键声和压抑的环境音

下集提示词（解决方案场景）: @上集尾帧，同一位8岁的中国女孩，齐肩黑色直发扎着马尾，穿着深圳夏季校服（白色短袖衬衫配深蓝色短裙和白色运动鞋），在同一间深圳现代家庭客厅里，坐在黑色立式钢琴前的棕色琴凳上，银色iPad放在钢琴的琴谱架上显示@练琴页，屏幕上有彩色音符和可爱的卡通角色，同一位35岁的妈妈，中长黑色直发，穿着米色休闲衬衫配深蓝色牛仔裤，坐在孩子旁边的沙发上，微笑着说"宝贝，我们一起用这个App试试吧"，孩子眼神专注地看着iPad屏幕，跟着App的游戏化指引，手指流畅地在黑白琴键上移动，嘴里轻声跟着App唱"哆来咪发索"，App发出鼓励的音效"太棒了！"，孩子成功弹奏出完整的小星星旋律，抬起头露出灿烂的笑容说"妈妈，我学会了！"，妈妈竖起大拇指，两人击掌庆祝，客厅布局完全一致（米色布艺沙发、浅色木地板、白色纱帘、暖色调装饰画），同样温暖的午后阳光透过白色纱帘洒进来，在木地板和钢琴表面形成柔和的光影，温馨明亮偏暖的色调，氛围从紧张转为和谐快乐，治愈系温馨家庭风，镜头从侧面中景缓缓推进到孩子和妈妈开心的面部特写，背景有流畅的琴键声、App的鼓励音效和欢快的小星星旋律

请直接输出，不要有其他解释。"""
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '生成两段式脚本', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            content = result['choices'][0]['message']['content'].strip()
            
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
            
            product_image_mapping = {
                '@logo': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/logo.png',
                '@启动页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/启动页.png',
                '@玩法页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/玩法页.png',
                '@练琴页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/练琴页.png',
                '@选择关卡页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页.png',
                '@选择关卡页2': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页2.png'
            }
            
            import re
            
            part1_images = []
            part1_prompt = two_part_info.get('part1_seedance_prompt', '')
            for ref_name, img_path in product_image_mapping.items():
                if ref_name in part1_prompt and os.path.exists(img_path):
                    if img_path not in part1_images:
                        part1_images.append(img_path)
            
            part2_images = []
            part2_prompt = two_part_info.get('part2_seedance_prompt', '')
            for ref_name, img_path in product_image_mapping.items():
                if ref_name in part2_prompt and os.path.exists(img_path):
                    if img_path not in part2_images:
                        part2_images.append(img_path)
            
            two_part_info['part1_product_images'] = part1_images
            two_part_info['part2_product_images'] = part2_images
            
            return two_part_info
            
        except Exception as e:
            return {
                'core_story': f'Error: {str(e)}',
                'part1_content': 'Error analyzing',
                'part2_content': 'Error analyzing',
                'part1_seedance_prompt': 'Error generating',
                'part2_seedance_prompt': 'Error generating'
            }
    
    def generate_seedance_prompt_for_condensed(self, condensed_script_info):
        """
        生成浓缩脚本的 Seedance 2.0 中文提示词（可以使用 @ 引用产品图片）
        
        参数:
        - condensed_script_info: 浓缩脚本信息（包含核心故事、关键画面、完整提示词）
        
        返回:
        - dict: {'seedance_prompt': str, 'product_images': list}
        """
        
        core_story = condensed_script_info.get('core_story', '')
        complete_prompt = condensed_script_info.get('complete_prompt', '')
        
        prompt = f"""你是一个专业的 Seedance 2.0 提示词生成专家。请根据以下浓缩脚本信息，生成一个符合 Seedance 2.0 规范的中文提示词。

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
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
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
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=data)
            response.raise_for_status()
            result = response.json()
            usage = result.get('usage', {})
            _log_token_usage(self.model, '生成浓缩Seedance提示词', usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0))
            seedance_prompt = result['choices'][0]['message']['content'].strip()
            
            product_image_mapping = {
                '@logo': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/logo.png',
                '@启动页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/启动页.png',
                '@玩法页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/玩法页.png',
                '@练琴页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/练琴页.png',
                '@选择关卡页': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页.png',
                '@选择关卡页2': '/Users/ssg/Documents/CodeX/AdVideoSystem/resource/pic/选择关卡页2.png'
            }
            
            product_images = []
            for ref_name, img_path in product_image_mapping.items():
                if ref_name in seedance_prompt and os.path.exists(img_path):
                    if img_path not in product_images:
                        product_images.append(img_path)
            
            return {
                'seedance_prompt': seedance_prompt,
                'product_images': product_images
            }
            
        except Exception as e:
            return {
                'seedance_prompt': f"生成失败: {str(e)}",
                'product_images': []
            }
