import os

import cv2
from scenedetect import SceneManager, VideoManager
from scenedetect.detectors import ContentDetector


class VideoProcessor:
    def __init__(self, video_path, output_dir):
        self.video_path = video_path
        self.output_dir = output_dir
        self.frames_dir = os.path.join(output_dir, "frames")
        os.makedirs(self.frames_dir, exist_ok=True)

    def _write_frame(self, filename, frame):
        frame_path = os.path.join(self.frames_dir, filename)
        if not cv2.imwrite(frame_path, frame):
            return None
        return frame_path

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
        frames_info = []

        for i, (start_time, end_time) in enumerate(scenes):
            start_frame = int(start_time.get_frames())
            end_frame = int(end_time.get_frames())
            mid_frame = (start_frame + end_frame) // 2
            scene_prefix = f"scene_{i + 1:03d}"

            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            ret, first_frame = cap.read()
            first_frame_path = None
            if ret:
                first_frame_path = self._write_frame(f"{scene_prefix}_start.jpg", first_frame)

            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
            ret, frame = cap.read()
            keyframe_path = None
            if ret:
                keyframe_path = self._write_frame(f"{scene_prefix}_keyframe.jpg", frame)

            cap.set(cv2.CAP_PROP_POS_FRAMES, max(end_frame - 1, start_frame))
            ret, last_frame = cap.read()
            last_frame_path = None
            if ret:
                last_frame_path = self._write_frame(f"{scene_prefix}_end.jpg", last_frame)

            frames_info.append({
                "scene_number": i + 1,
                "start_time": start_time.get_seconds(),
                "end_time": end_time.get_seconds(),
                "duration": (end_time - start_time).get_seconds(),
                "keyframe_path": keyframe_path,
                "first_frame_path": first_frame_path,
                "last_frame_path": last_frame_path,
            })

        if frames_info:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, first_frame = cap.read()
            if ret:
                self._write_frame("global_first.jpg", first_frame)

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(total_frames - 1, 0))
            ret, last_frame = cap.read()
            if ret:
                self._write_frame("global_last.jpg", last_frame)

        cap.release()
        return frames_info
