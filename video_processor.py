import os
import cv2
from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector

class VideoProcessor:
    def __init__(self, video_path, output_dir):
        self.video_path = video_path
        self.output_dir = output_dir
        self.frames_dir = os.path.join(output_dir, 'frames')
        os.makedirs(self.frames_dir, exist_ok=True)
    
    def detect_scenes(self, threshold=27.0):
        video_manager = VideoManager([self.video_path])
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        
        video_manager.start()
        scene_manager.detect_scenes(video_manager)
        scene_list = scene_manager.get_scene_list()
        video_manager.release()
        
        return scene_list
    
    def extract_keyframes(self, scenes):
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        frames_info = []
        
        for i, (start_time, end_time) in enumerate(scenes):
            start_frame = int(start_time.get_frames())
            end_frame = int(end_time.get_frames())
            mid_frame = (start_frame + end_frame) // 2
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            ret, first_frame = cap.read()
            first_frame_path = None
            if ret:
                first_frame_path = os.path.join(self.frames_dir, f'镜头{i+1}_开始.jpg')
                cv2.imwrite(first_frame_path, first_frame)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ret, frame = cap.read()
            keyframe_path = None
            if ret:
                keyframe_path = os.path.join(self.frames_dir, f'镜头{i+1}_关键帧.jpg')
                cv2.imwrite(keyframe_path, frame)
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, end_frame - 1)
            ret, last_frame = cap.read()
            last_frame_path = None
            if ret:
                last_frame_path = os.path.join(self.frames_dir, f'镜头{i+1}_结束.jpg')
                cv2.imwrite(last_frame_path, last_frame)
                
            frames_info.append({
                'scene_number': i + 1,
                'start_time': start_time.get_seconds(),
                'end_time': end_time.get_seconds(),
                'duration': (end_time - start_time).get_seconds(),
                'keyframe_path': keyframe_path,
                'first_frame_path': first_frame_path,
                'last_frame_path': last_frame_path
            })
        
        if frames_info:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = cap.read()
            if ret:
                first_frame_path = os.path.join(self.frames_dir, 'global_first.jpg')
                cv2.imwrite(first_frame_path, first_frame)
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
            ret, last_frame = cap.read()
            if ret:
                last_frame_path = os.path.join(self.frames_dir, 'global_last.jpg')
                cv2.imwrite(last_frame_path, last_frame)
        
        cap.release()
        return frames_info
