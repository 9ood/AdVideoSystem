let currentTaskId = null;

document.getElementById("videoInput").addEventListener("change", function(event) {
    const file = event.target.files[0];
    if (file) {
        document.getElementById("fileName").textContent = `已选择：${file.name}，马上开始上传。`;
        uploadVideo(file);
    }
});

async function uploadVideo(file) {
    const formData = new FormData();
    formData.append("video", file);

    showSection("processingSection");
    updateProgress(10, "正在上传视频...");

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            currentTaskId = data.task_id;
            updateProgress(30, "上传完成，马上开始分析视频...");
            processVideo(currentTaskId);
        } else {
            showError(data.error || "上传失败");
        }
    } catch (error) {
        showError(`网络错误：${error.message}`);
    }
}

async function processVideo(taskId) {
    updateProgress(45, "正在检测镜头和关键帧...");

    try {
        const response = await fetch(`/process/${taskId}`, {
            method: "POST"
        });

        const data = await response.json();

        if (response.ok) {
            updateProgress(100, "处理完成，正在准备下载结果...");
            setTimeout(() => {
                showResult(data.scenes_count, taskId);
            }, 400);
        } else {
            showError(data.error || "处理失败");
        }
    } catch (error) {
        showError(`处理出错：${error.message}`);
    }
}

function showSection(sectionId) {
    const sections = ["uploadSection", "processingSection", "resultSection", "errorSection"];
    sections.forEach((id) => {
        document.getElementById(id).classList.add("hidden");
    });
    document.getElementById(sectionId).classList.remove("hidden");
}

function updateProgress(percent, text) {
    document.getElementById("progressFill").style.width = `${percent}%`;
    document.getElementById("progressText").textContent = text;
}

function showResult(sceneCount, taskId) {
    showSection("resultSection");
    document.getElementById("sceneCount").textContent = sceneCount;

    document.getElementById("downloadBtn").onclick = function() {
        window.location.href = `/download/${taskId}`;
    };

    document.getElementById("downloadCleanBtn").onclick = function() {
        window.location.href = `/download_clean/${taskId}`;
    };
}

function showError(message) {
    showSection("errorSection");
    document.getElementById("errorMessage").textContent = message;
}
