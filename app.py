import os
import zipfile
import shutil
import json
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import uuid
from video_processor import VideoProcessor
from ai_analyzer import AIAnalyzer
from excel_generator import ExcelGenerator

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if file and allowed_file(file.filename):
        task_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_{filename}")
        file.save(video_path)
        
        return jsonify({
            'task_id': task_id,
            'message': '文件上传成功，开始处理...'
        })
    
    return jsonify({'error': '不支持的文件格式'}), 400

@app.route('/process/<task_id>', methods=['POST'])
def process_video(task_id):
    try:
        upload_files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.startswith(task_id)]
        if not upload_files:
            return jsonify({'error': '找不到上传的视频'}), 404
        
        video_filename = upload_files[0]
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        output_dir = os.path.join(app.config['OUTPUT_FOLDER'], task_id)
        os.makedirs(output_dir, exist_ok=True)
        
        original_name = video_filename.replace(f"{task_id}_", "").rsplit('.', 1)[0]
        with open(os.path.join(output_dir, 'original_name.txt'), 'w', encoding='utf-8') as f:
            f.write(original_name)
        
        processor = VideoProcessor(video_path, output_dir)
        scenes = processor.detect_scenes()
        frames_info = processor.extract_keyframes(scenes)
        
        api_key = os.getenv('OPENROUTER_API_KEY')
        model = os.getenv('GEMINI_MODEL', 'google/gemini-3-flash-preview')
        analyzer = AIAnalyzer(api_key, model)
        
        analyzed_scenes = []
        for i, frame_info in enumerate(frames_info):
            prompt = analyzer.analyze_frame(frame_info['keyframe_path'])
            script = analyzer.generate_script(frame_info['keyframe_path'], prompt)
            complete_prompt = analyzer.generate_complete_prompt(
                prompt, 
                script, 
                frame_info['duration']
            )
            seedance_result = analyzer.generate_seedance_prompt_for_scene(
                prompt,
                script,
                frame_info.get('first_frame_path'),
                frame_info.get('last_frame_path'),
                i + 1
            )
            analyzed_scenes.append({
                'scene_number': i + 1,
                'start_time': frame_info['start_time'],
                'end_time': frame_info['end_time'],
                'duration': frame_info['duration'],
                'keyframe_path': frame_info['keyframe_path'],
                'prompt': prompt,
                'script': script,
                'complete_prompt': complete_prompt,
                'seedance_prompt': seedance_result
            })
        
        global_info = analyzer.analyze_global_context(
            frames_info[0]['keyframe_path'] if frames_info else None,
            frames_info[-1]['keyframe_path'] if frames_info else None
        )
        
        keyframe_paths = [frame_info['keyframe_path'] for frame_info in frames_info]
        condensed_script = analyzer.generate_condensed_script(analyzed_scenes, keyframe_paths)
        
        if condensed_script:
            condensed_seedance_result = analyzer.generate_seedance_prompt_for_condensed(condensed_script)
            condensed_script['seedance_prompt'] = condensed_seedance_result.get('seedance_prompt', '')
            condensed_script['product_images'] = condensed_seedance_result.get('product_images', [])
        
        two_part_script = analyzer.generate_two_part_script(analyzed_scenes, keyframe_paths)
        
        excel_gen = ExcelGenerator(output_dir)
        excel_path = excel_gen.generate(global_info, analyzed_scenes, condensed_script, two_part_script)
        
        analysis_data = {
            'global_info': global_info,
            'analyzed_scenes': analyzed_scenes,
            'condensed_script': condensed_script,
            'two_part_script': two_part_script
        }
        with open(os.path.join(output_dir, 'analysis_data.json'), 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'scenes_count': len(analyzed_scenes),
            'download_url': f'/download/{task_id}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<task_id>')
def download_result(task_id):
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], task_id)
    excel_path = os.path.join(output_dir, 'video_script.xlsx')
    frames_dir = os.path.join(output_dir, 'frames')
    
    original_name = '分析结果'
    name_file = os.path.join(output_dir, 'original_name.txt')
    if os.path.exists(name_file):
        with open(name_file, 'r', encoding='utf-8') as f:
            original_name = f.read().strip()
    
    zip_filename = f'AI翻拍_{original_name}_完整包.zip'
    zip_path = os.path.join(output_dir, zip_filename)
    excel_filename = f'AI翻拍_{original_name}_完整版.xlsx'
    
    if not os.path.exists(excel_path):
        return jsonify({'error': 'Excel文件不存在'}), 404
    
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(excel_path, excel_filename)
            
            if os.path.exists(frames_dir):
                for filename in os.listdir(frames_dir):
                    if filename.startswith('镜头') and filename.endswith('.jpg'):
                        file_path = os.path.join(frames_dir, filename)
                        zipf.write(file_path, os.path.join('关键帧', filename))
        
        return send_file(zip_path, as_attachment=True, download_name=zip_filename)
    
    except Exception as e:
        return jsonify({'error': f'生成ZIP文件失败: {str(e)}'}), 500

@app.route('/download_clean/<task_id>')
def download_clean_result(task_id):
    output_dir = os.path.join(app.config['OUTPUT_FOLDER'], task_id)
    
    original_name = '分析结果'
    name_file = os.path.join(output_dir, 'original_name.txt')
    if os.path.exists(name_file):
        with open(name_file, 'r', encoding='utf-8') as f:
            original_name = f.read().strip()
    
    clean_excel_filename = f'AI翻拍_{original_name}_纯净版.xlsx'
    clean_excel_path = os.path.join(output_dir, clean_excel_filename)
    
    if os.path.exists(clean_excel_path):
        return send_file(clean_excel_path, as_attachment=True, download_name=clean_excel_filename)
    
    try:
        analysis_data_path = os.path.join(output_dir, 'analysis_data.json')
        if not os.path.exists(analysis_data_path):
            return jsonify({'error': '找不到分析数据'}), 404
        
        with open(analysis_data_path, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)
        
        excel_gen = ExcelGenerator(output_dir)
        excel_gen.generate(
            analysis_data['global_info'],
            analysis_data['analyzed_scenes'],
            analysis_data['condensed_script'],
            analysis_data['two_part_script'],
            clean_mode=True
        )
        
        original_excel = os.path.join(output_dir, 'video_script.xlsx')
        if os.path.exists(original_excel):
            shutil.copy(original_excel, clean_excel_path)
        
        return send_file(clean_excel_path, as_attachment=True, download_name=clean_excel_filename)
    
    except Exception as e:
        return jsonify({'error': f'生成纯净版Excel失败: {str(e)}'}), 500

@app.route('/token_usage_page')
def token_usage_page():
    return render_template('token_usage.html')

@app.route('/token_usage')
def token_usage():
    log_path = os.path.join(os.path.dirname(__file__), 'token_log.json')
    if not os.path.exists(log_path):
        logs = []
    else:
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except Exception:
            logs = []

    total_input = sum(r.get('input_tokens', 0) for r in logs)
    total_output = sum(r.get('output_tokens', 0) for r in logs)
    total_cost = sum(r.get('cost_usd', 0) for r in logs)

    today = __import__('datetime').date.today().strftime('%Y-%m-%d')
    today_logs = [r for r in logs if r.get('time', '').startswith(today)]
    today_input = sum(r.get('input_tokens', 0) for r in today_logs)
    today_output = sum(r.get('output_tokens', 0) for r in today_logs)
    today_cost = sum(r.get('cost_usd', 0) for r in today_logs)

    return jsonify({
        'total': {
            'input_tokens': total_input,
            'output_tokens': total_output,
            'total_tokens': total_input + total_output,
            'cost_usd': round(total_cost, 6)
        },
        'today': {
            'date': today,
            'input_tokens': today_input,
            'output_tokens': today_output,
            'total_tokens': today_input + today_output,
            'cost_usd': round(today_cost, 6)
        },
        'records': list(reversed(logs))
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
