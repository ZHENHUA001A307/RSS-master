from pathlib import Path

p = Path('index.html')
text = p.read_text(encoding='utf-8')

# ========== 1. 任务行加 ✏️ 按钮 ==========
old1 = """'<button class="primary small" onclick="editTaskProgress"""
new1 = """'<button class="gray small" onclick="openTaskModal(\\'' + name + '\\', \\'' + safeId + '\\')">✏️ 配置</button>' +
          '<button class="primary small" onclick="editTaskProgress"""

if old1 in text:
    text = text.replace(old1, new1, 1)
    print('OK: button')
else:
    print('WARN: button anchor missing')

# ========== 2. 插入 taskModal HTML ==========
old2 = '<div class="modal-bg" id="healthModal">'
new2 = '''<div class="modal-bg" id="taskModal">
  <div class="modal" style="max-width:700px">
    <div class="modal-header">
      <h3 id="taskModalTitle">编辑任务</h3>
      <button class="gray small" onclick="closeTaskModal()">✕</button>
    </div>
    <div class="modal-body" id="taskModalBody">加载中...</div>
    <div class="modal-footer">
      <button class="gray" onclick="closeTaskModal()">取消</button>
      <button class="primary" onclick="saveTaskConfig()">保存</button>
    </div>
  </div>
</div>

'''

if 'id="taskModal"' in text:
    print('SKIP: taskModal exists')
elif old2 in text:
    text = text.replace(old2, new2 + old2, 1)
    print('OK: taskModal')
else:
    print('WARN: taskModal anchor missing')

# ========== 3. 插入 JS 函数 ==========
old3 = 'async function triggerTask(name, taskId) {'
new3 = '''let currentTaskRepo = null;
let currentTaskId = null;
let currentTaskData = null;

function openTaskModal(name, taskId) {
  currentTaskRepo = name;
  currentTaskId = taskId;
  const info = repoInfos[name];
  if (!info || !info.tasks) return;
  const task = info.tasks.find(t => t.id === taskId);
  if (!task) return;
  const cfg = config.repos[name];
  const cfgTask = (cfg.tasks || []).find(t => t.id === taskId) || {};
  currentTaskData = {
    label: cfgTask.label || task.label || '',
    lang: cfgTask.lang || task.lang || '',
    cron: cfgTask.cron || task.cron || '',
    batch_size: cfgTask.batch_size || task.batch_size || 15,
    slice_mode: cfgTask.slice_mode || 'by_count',
    input_file: cfgTask.input_file || '',
    progress_file: cfgTask.progress_file || '',
    prompt_file: cfgTask.prompt_file || '',
    model_name: cfgTask.model_name || 'deepseek-v4-pro'
  };
  document.getElementById('taskModalTitle').textContent = '编辑任务：' + currentTaskData.label;
  renderTaskModal();
  document.getElementById('taskModal').classList.add('visible');
}

function closeTaskModal() {
  document.getElementById('taskModal').classList.remove('visible');
  currentTaskRepo = null;
  currentTaskId = null;
  currentTaskData = null;
}

function renderTaskModal() {
  const d = currentTaskData;
  const html =
    '<div class="form-row"><label>显示名</label><input type="text" id="tf_label" value="' + escapeHtml(d.label) + '"></div>' +
    '<div class="form-row"><label>语言前缀</label><input type="text" id="tf_lang" value="' + escapeHtml(d.lang) + '"><span class="hint">feed 标题前缀</span></div>' +
    '<div class="form-row"><label>Cron</label><input type="text" class="cron-input" style="width:160px" id="tf_cron" value="' + escapeHtml(d.cron) + '"></div>' +
    '<div class="form-row"><label>批次大小</label><input type="number" class="num-input" id="tf_batch" value="' + d.batch_size + '"><span class="hint">每次推几行</span></div>' +
    '<div class="form-row"><label>切片模式</label><select id="tf_slice" style="flex:1;padding:5px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px">' +
      '<option value="by_count"' + (d.slice_mode === 'by_count' ? ' selected' : '') + '>by_count（按条数）</option>' +
      '<option value="by_topic"' + (d.slice_mode === 'by_topic' ? ' selected' : '') + '>by_topic（按话题）</option>' +
    '</select></div>' +
    '<div class="form-row"><label>输入文件</label><input type="text" id="tf_input" value="' + escapeHtml(d.input_file) + '"></div>' +
    '<div class="form-row"><label>进度文件</label><input type="text" id="tf_progress" value="' + escapeHtml(d.progress_file) + '"></div>' +
    '<div class="form-row"><label>提示词文件</label><input type="text" id="tf_prompt" value="' + escapeHtml(d.prompt_file) + '"></div>' +
    '<div class="form-row"><label>模型</label><input type="text" id="tf_model" value="' + escapeHtml(d.model_name) + '"></div>' +
    '<div class="hint" style="margin-top:12px">保存后会更新 repos.json 和 workflow yml。请手动点「应用到各仓库」和「批量 Push」。</div>';
  document.getElementById('taskModalBody').innerHTML = html;
}

async function saveTaskConfig() {
  if (!currentTaskRepo || !currentTaskId) return;
  const fields = {
    label: document.getElementById('tf_label').value.trim(),
    lang: document.getElementById('tf_lang').value.trim(),
    cron: document.getElementById('tf_cron').value.trim(),
    batch_size: parseInt(document.getElementById('tf_batch').value) || 15,
    slice_mode: document.getElementById('tf_slice').value,
    input_file: document.getElementById('tf_input').value.trim(),
    progress_file: document.getElementById('tf_progress').value.trim(),
    prompt_file: document.getElementById('tf_prompt').value.trim(),
    model_name: document.getElementById('tf_model').value.trim()
  };
  if (fields.progress_file !== currentTaskData.progress_file) {
    if (!confirm('你修改了进度文件路径。\\n\\n这会切换进度指针，相当于从新文件读取进度。\\n旧进度仍在旧文件里，但不会被读取。\\n\\n确定继续？')) return;
  }
  log('⏳ 保存任务配置：' + currentTaskRepo + '/' + currentTaskId);
  const r = await api('/api/task-config/' + currentTaskRepo + '/' + currentTaskId, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(fields)
  });
  if (!r.ok) {
    log('❌ ' + (r.error || '保存失败'));
    return;
  }
  log('✅ ' + r.output);
  if (r.warnings && r.warnings.length > 0) {
    for (const w of r.warnings) {
      log('⚠️ ' + w);
    }
  }
  closeTaskModal();
  await reload();
}

'''

if 'function openTaskModal' in text:
    print('SKIP: JS functions exist')
elif old3 in text:
    text = text.replace(old3, new3 + old3, 1)
    print('OK: JS functions')
else:
    print('WARN: JS anchor missing')

p.write_text(text, encoding='utf-8')
print('DONE')