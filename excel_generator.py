import os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

class ExcelGenerator:
    def __init__(self, output_dir):
        self.output_dir = output_dir
    
    def generate(self, global_info, scenes, condensed_script=None):
        wb = Workbook()
        
        ws_global = wb.active
        ws_global.title = "全局信息"
        
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        
        ws_global['A1'] = '项目'
        ws_global['B1'] = '内容'
        ws_global['A1'].fill = header_fill
        ws_global['B1'].fill = header_fill
        ws_global['A1'].font = header_font
        ws_global['B1'].font = header_font
        
        global_data = [
            ['视频总时长', f"{scenes[-1]['end_time']:.2f}秒" if scenes else '0秒'],
            ['总镜头数', len(scenes)],
            ['整体风格', global_info.get('style', '')],
            ['主角描述', global_info.get('main_character', '')],
            ['场景描述', global_info.get('main_scene', '')],
            ['首帧图片', './frames/global_first.jpg'],
            ['尾帧图片', './frames/global_last.jpg']
        ]
        
        for i, row_data in enumerate(global_data, start=2):
            ws_global[f'A{i}'] = row_data[0]
            ws_global[f'B{i}'] = row_data[1]
        
        ws_global.column_dimensions['A'].width = 20
        ws_global.column_dimensions['B'].width = 60
        
        ws_scenes = wb.create_sheet(title="镜头详情")
        
        headers = ['镜头编号', '开始时间(秒)', '结束时间(秒)', '时长(秒)', '镜头类型', 'Sora提示词(场景描述)', '台词脚本', '完整Sora提示词(可直接使用)', '关键帧路径']
        for col, header in enumerate(headers, start=1):
            cell = ws_scenes.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
        
        for i, scene in enumerate(scenes, start=2):
            ws_scenes.cell(row=i, column=1, value=scene['scene_number'])
            ws_scenes.cell(row=i, column=2, value=f"{scene['start_time']:.2f}")
            ws_scenes.cell(row=i, column=3, value=f"{scene['end_time']:.2f}")
            ws_scenes.cell(row=i, column=4, value=f"{scene['duration']:.2f}")
            
            shot_type = self.extract_shot_type(scene['prompt'])
            ws_scenes.cell(row=i, column=5, value=shot_type)
            
            ws_scenes.cell(row=i, column=6, value=scene['prompt'])
            
            script = scene.get('script', '')
            ws_scenes.cell(row=i, column=7, value=script)
            
            complete_prompt = scene.get('complete_prompt', '')
            ws_scenes.cell(row=i, column=8, value=complete_prompt)
            
            relative_path = os.path.relpath(scene['keyframe_path'], self.output_dir)
            ws_scenes.cell(row=i, column=9, value=f"./{relative_path}")
        
        ws_scenes.column_dimensions['A'].width = 12
        ws_scenes.column_dimensions['B'].width = 15
        ws_scenes.column_dimensions['C'].width = 15
        ws_scenes.column_dimensions['D'].width = 12
        ws_scenes.column_dimensions['E'].width = 15
        ws_scenes.column_dimensions['F'].width = 60
        ws_scenes.column_dimensions['G'].width = 50
        ws_scenes.column_dimensions['H'].width = 100
        ws_scenes.column_dimensions['I'].width = 40
        
        for row in ws_scenes.iter_rows(min_row=2, max_row=len(scenes)+1):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        
        if condensed_script:
            ws_condensed = wb.create_sheet(title="浓缩脚本")
            
            ws_condensed['A1'] = '项目'
            ws_condensed['B1'] = '内容'
            ws_condensed['A1'].fill = header_fill
            ws_condensed['B1'].fill = header_fill
            ws_condensed['A1'].font = header_font
            ws_condensed['B1'].font = header_font
            
            condensed_data = [
                ['视频时长', condensed_script.get('duration', '10-15秒')],
                ['核心故事', condensed_script.get('core_story', '')],
                ['关键画面1 (0-5秒)', condensed_script.get('key_scene_1', '')],
                ['关键画面2 (5-10秒)', condensed_script.get('key_scene_2', '')],
                ['关键画面3 (10-15秒)', condensed_script.get('key_scene_3', '')],
                ['完整Sora提示词', condensed_script.get('complete_prompt', '')]
            ]
            
            for i, row_data in enumerate(condensed_data, start=2):
                ws_condensed[f'A{i}'] = row_data[0]
                ws_condensed[f'B{i}'] = row_data[1]
                ws_condensed[f'B{i}'].alignment = Alignment(wrap_text=True, vertical='top')
            
            ws_condensed.column_dimensions['A'].width = 25
            ws_condensed.column_dimensions['B'].width = 100
            
            ws_condensed.row_dimensions[7].height = 80
        
        excel_path = os.path.join(self.output_dir, 'video_script.xlsx')
        wb.save(excel_path)
        
        return excel_path
    
    def extract_shot_type(self, prompt):
        prompt_lower = prompt.lower()
        if 'close-up' in prompt_lower or 'close up' in prompt_lower:
            return '特写'
        elif 'medium shot' in prompt_lower or 'mid shot' in prompt_lower:
            return '中景'
        elif 'wide shot' in prompt_lower or 'long shot' in prompt_lower or 'full shot' in prompt_lower:
            return '全景'
        elif 'extreme close-up' in prompt_lower:
            return '大特写'
        else:
            return '中景'
