import requests
import base64
import os

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
    
    def generate_condensed_script(self, analyzed_scenes, keyframe_paths):
        """
        生成浓缩脚本（10-15秒版本）
        
        参数:
        - analyzed_scenes: 所有镜头的分析结果列表
        - keyframe_paths: 关键帧图片路径列表（用于AI分析）
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
        
        prompt = f"""你是一个专业的视频导演和编剧。现在有一个{total_duration:.1f}秒的视频，包含{len(analyzed_scenes)}个镜头。你的任务是：把这个视频的故事浓缩成一个10-15秒的精简版本。

重要：这不是简单的拼接或缩短，而是要重新创作一个新的10-15秒视频，保留原视频的核心故事、情感和关键台词。

原视频所有镜头的完整信息:
{scenes_summary}

请按以下格式输出:

核心故事: [用1-2句话概括整个视频讲了什么故事，传达了什么情感]

关键画面1: [0-5秒的画面内容，用中文描述]
关键画面2: [5-10秒的画面内容，用中文描述]
关键画面3: [10-15秒的画面内容，用中文描述]

完整提示词: [用英文写一个完整的Sora视频生成提示词，这个提示词要包含所有信息，让Sora可以直接生成视频。要求：
1. 描述一个连贯的10-15秒视频，包含开头、发展、结尾
2. 必须是中国人物、中国场景
3. 详细描述人物动作、表情、环境细节
4. 如果原视频有台词，要在提示词中包含浓缩后的关键台词（用中文，并标注拼音或英文翻译）
5. 台词要自然地融入画面描述中，格式如: saying "台词内容" (English translation)
6. 写成一个流畅的段落，不要分点列举
7. 包含风格、光线、情感等细节]

例子（仅供参考格式）:
完整提示词: A continuous 15-second cinematic sequence of a young Chinese woman learning piano in a modern Beijing apartment. The video begins with her looking at her smartphone with excitement, saying "今天我要开始学钢琴了!" (Today I'm going to start learning piano!), then smoothly transitions to a close-up of her slender fingers touching the piano keys as she whispers "原来弹琴是这种感觉" (So this is what playing feels like), and concludes with a wide shot of her playing confidently with a joyful smile, exclaiming "我终于学会了!" (I finally learned it!). The style is warm and inspiring, with soft natural afternoon lighting streaming through large windows, capturing an intimate journey of discovery and achievement.
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
            content = result['choices'][0]['message']['content'].strip()
            
            # 解析AI返回的内容
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
