import os
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
        
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], upload_files[0])
        output_dir = os.path.join(app.config['OUTPUT_FOLDER'], task_id)
        os.makedirs(output_dir, exist_ok=True)
        
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
            analyzed_scenes.append({
                'scene_number': i + 1,
                'start_time': frame_info['start_time'],
                'end_time': frame_info['end_time'],
                'duration': frame_info['duration'],
                'keyframe_path': frame_info['keyframe_path'],
                'prompt': prompt,
                'script': script,
                'complete_prompt': complete_prompt
            })
        
        global_info = analyzer.analyze_global_context(
            frames_info[0]['keyframe_path'] if frames_info else None,
            frames_info[-1]['keyframe_path'] if frames_info else None
        )
        
        keyframe_paths = [frame_info['keyframe_path'] for frame_info in frames_info]
        condensed_script = analyzer.generate_condensed_script(analyzed_scenes, keyframe_paths)
        
        excel_gen = ExcelGenerator(output_dir)
        excel_path = excel_gen.generate(global_info, analyzed_scenes, condensed_script)
        
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
    
    if os.path.exists(excel_path):
        return send_file(excel_path, as_attachment=True)
    
    return jsonify({'error': '文件不存在'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
