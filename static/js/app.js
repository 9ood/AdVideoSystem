let currentTaskId = null;

document.getElementById('videoInput').addEventListener('change', function(e) {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('fileName').textContent = `已选择: ${file.name}`;
        uploadVideo(file);
    }
});

async function uploadVideo(file) {
    const formData = new FormData();
    formData.append('video', file);
    
    showSection('processingSection');
    updateProgress(10, '正在上传视频...');
    
    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentTaskId = data.task_id;
            updateProgress(30, '上传完成，开始分析视频...');
            processVideo(currentTaskId);
        } else {
            showError(data.error || '上传失败');
        }
    } catch (error) {
        showError('网络错误: ' + error.message);
    }
}

async function processVideo(taskId) {
    updateProgress(40, '正在检测镜头...');
    
    try {
        const response = await fetch(`/process/${taskId}`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            updateProgress(100, '处理完成！');
            setTimeout(() => {
                showResult(data.scenes_count, taskId);
            }, 500);
        } else {
            showError(data.error || '处理失败');
        }
    } catch (error) {
        showError('处理错误: ' + error.message);
    }
}

function showSection(sectionId) {
    const sections = ['uploadSection', 'processingSection', 'resultSection', 'errorSection'];
    sections.forEach(id => {
        document.getElementById(id).style.display = 'none';
    });
    document.getElementById(sectionId).style.display = 'block';
}

function updateProgress(percent, text) {
    document.getElementById('progressFill').style.width = percent + '%';
    document.getElementById('progressText').textContent = text;
}

function showResult(sceneCount, taskId) {
    showSection('resultSection');
    document.getElementById('sceneCount').textContent = sceneCount;
    
    document.getElementById('downloadBtn').onclick = function() {
        window.location.href = `/download/${taskId}`;
    };
    
    document.getElementById('downloadCleanBtn').onclick = function() {
        window.location.href = `/download_clean/${taskId}`;
    };
}

function showError(message) {
    showSection('errorSection');
    document.getElementById('errorMessage').textContent = message;
}
