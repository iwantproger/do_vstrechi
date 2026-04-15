/* ═══════════════════════════════════════════════════
   KANBAN TASKS
═══════════════════════════════════════════════════ */
let tasksData = { backlog: [], in_progress: [], done: [] };
let editingTaskId = null;
let deletingTaskId = null;
let currentTags = [];
let sortableInstances = [];
var viewingTaskId = null;

/* ── Multi-select state ───────────────────────────── */
let selectedTaskIds = new Set();
let selectMode = false;

async function loadTasks() {
  try {
    tasksData = await api('GET', '/api/admin/tasks');
    renderKanban();
  } catch (err) {
    console.error('Failed to load tasks', err);
    showNotification('Ошибка загрузки задач', 'error');
  }
}

function renderKanban() {
  ['backlog', 'in_progress', 'done'].forEach(function(status) {
    var col = document.getElementById('col-' + status);
    var count = document.getElementById('count-' + status);
    var tasks = tasksData[status] || [];
    count.textContent = tasks.length;
    col.innerHTML = tasks.map(renderTaskCard).join('');
  });
  initSortable();
  restoreSelection();
}

function renderTaskCard(task) {
  var tags = (task.tags || []).map(function(t) {
    return '<span class="task-tag ' + escHtml(t) + '">' + escHtml(t) + '</span>';
  }).join('');
  var desc = task.description_plain || task.description || '';
  var sourceLabel = { manual: '', git_commit: '\uD83D\uDCC2 git', ai_generated: '\uD83E\uDD16 AI', github_issue: '\uD83D\uDC19 issue' };
  var srcText = sourceLabel[task.source] || '';
  var shortId = task.id ? '#' + task.id.slice(0, 8) : '';
  return '<div class="task-card" data-id="' + escHtml(task.id) + '" data-source="' + escHtml(task.source) + '">'
    + '<div class="select-check">&#x2713;</div>'
    + '<div class="task-card-header">'
    + '<div class="task-card-title">' + escHtml(task.title) + '</div>'
    + '<span class="task-card-id">' + escHtml(shortId) + '</span>'
    + '</div>'
    + (desc ? '<div class="task-card-desc">' + escHtml(desc) + '</div>' : '')
    + (tags ? '<div class="task-card-tags">' + tags + '</div>' : '')
    + (srcText ? '<div class="task-card-source">' + srcText + '</div>' : '')
    + '<div class="task-card-actions">'
    + '<button class="task-edit-btn" data-id="' + escHtml(task.id) + '" title="Редактировать" onclick="event.stopPropagation()">\u270F\uFE0F</button>'
    + '<button class="task-delete-btn" data-id="' + escHtml(task.id) + '" data-title="' + escHtml(task.title) + '" title="Удалить" onclick="event.stopPropagation()">\uD83D\uDDD1</button>'
    + '</div></div>';
}

function initSortable() {
  sortableInstances.forEach(function(s) { s.destroy(); });
  sortableInstances = [];

  ['backlog', 'in_progress', 'done'].forEach(function(status) {
    var el = document.getElementById('col-' + status);
    var instance = new Sortable(el, {
      group: 'kanban',
      animation: 200,
      ghostClass: 'sortable-ghost',
      dragClass: 'sortable-drag',
      disabled: selectMode,
      onEnd: async function(evt) {
        var taskId = evt.item.dataset.id;
        var newStatus = evt.to.closest('.kanban-column').dataset.status;
        var oldStatus = evt.from.closest('.kanban-column').dataset.status;
        var taskIds = Array.from(evt.to.children).map(function(c) { return c.dataset.id; });

        updateKanbanCounts();

        try {
          if (oldStatus !== newStatus) {
            await api('PATCH', '/api/admin/tasks/' + taskId, { status: newStatus });
          }
          await api('PATCH', '/api/admin/tasks/reorder', { status: newStatus, task_ids: taskIds });
        } catch (err) {
          console.error('Reorder failed', err);
          showNotification('Ошибка сохранения порядка', 'error');
          loadTasks();
        }
      }
    });
    sortableInstances.push(instance);
  });
}

function updateKanbanCounts() {
  ['backlog', 'in_progress', 'done'].forEach(function(status) {
    var col = document.getElementById('col-' + status);
    var count = document.getElementById('count-' + status);
    count.textContent = col.children.length;
  });
}

/* ── Multi-select ─────────────────────────────────── */
function toggleSelectMode() {
  selectMode = !selectMode;
  var board = document.querySelector('.kanban-board');
  var btn = document.getElementById('select-mode-btn');

  if (selectMode) {
    board.classList.add('select-mode');
    btn.classList.add('active');
    btn.innerHTML = '&#x2611; Режим выбора';
    sortableInstances.forEach(function(s) { s.option('disabled', true); });
  } else {
    board.classList.remove('select-mode');
    btn.classList.remove('active');
    btn.innerHTML = '&#x2610; Выбрать';
    sortableInstances.forEach(function(s) { s.option('disabled', false); });
    // Keep selection so user can copy after exiting mode
  }
}

function toggleTaskSelection(taskId, cardEl) {
  if (selectedTaskIds.has(taskId)) {
    selectedTaskIds.delete(taskId);
    cardEl.classList.remove('selected');
  } else {
    selectedTaskIds.add(taskId);
    cardEl.classList.add('selected');
  }
  updateSelectionToolbar();
}

function clearSelection() {
  selectedTaskIds.clear();
  document.querySelectorAll('.task-card.selected').forEach(function(el) {
    el.classList.remove('selected');
  });
  updateSelectionToolbar();
  if (selectMode) toggleSelectMode();
}

function updateSelectionToolbar() {
  var toolbar = document.getElementById('selection-toolbar');
  var countEl = document.getElementById('sel-count');
  if (!toolbar || !countEl) return;
  if (selectedTaskIds.size > 0) {
    toolbar.style.display = 'flex';
    countEl.textContent = selectedTaskIds.size;
  } else {
    toolbar.style.display = 'none';
  }
}

function restoreSelection() {
  selectedTaskIds.forEach(function(id) {
    var card = document.querySelector('.task-card[data-id="' + id + '"]');
    if (card) card.classList.add('selected');
  });
  updateSelectionToolbar();
}

function selectAllTasks() {
  selectedTaskIds.clear();
  document.querySelectorAll('.task-card').forEach(function(card) {
    var id = card.dataset.id;
    if (id) {
      selectedTaskIds.add(id);
      card.classList.add('selected');
    }
  });
  updateSelectionToolbar();
}

async function copySelectedTasks() {
  if (selectedTaskIds.size === 0) return;

  var tasks = [];
  ['backlog', 'in_progress', 'done'].forEach(function(status) {
    (tasksData[status] || []).forEach(function(t) {
      if (selectedTaskIds.has(t.id)) tasks.push(t);
    });
  });
  if (!tasks.length) return;

  var statusLabels = { backlog: 'Backlog', in_progress: 'В работе', done: 'Готово' };
  var sourceLabels = { manual: 'Manual', git_commit: 'Git commit', ai_generated: 'AI generated', github_issue: 'GitHub issue' };

  var text = '';

  if (tasks.length === 1) {
    text += '# Задача: ' + tasks[0].title + '\n\n';
  } else {
    text += '# Задачи к выполнению (' + tasks.length + ')\n\n';
  }

  tasks.forEach(function(task, i) {
    if (tasks.length > 1) {
      text += '---\n\n';
      text += '## ' + (i + 1) + '. ' + task.title + '\n\n';
    }

    text += '**Статус:** ' + (statusLabels[task.status] || task.status);
    if (task.tags && task.tags.length) {
      text += ' | **Теги:** ' + task.tags.join(', ');
    }
    text += '\n';
    if (task.source && task.source !== 'manual') {
      text += '**Источник:** ' + (sourceLabels[task.source] || task.source) + '\n';
    }
    text += '\n';

    if (task.description) {
      text += '### Техническое описание\n\n' + task.description + '\n\n';
    }
    if (task.description_plain && task.description_plain !== task.description) {
      text += '### Описание простым языком\n\n' + task.description_plain + '\n\n';
    }
    if (task.source_ref) {
      text += '**Ссылка:** ' + task.source_ref + '\n\n';
    }
  });

  var btn = document.querySelector('.selection-toolbar .btn-copy-bulk');
  var origHTML = btn ? btn.innerHTML : '';

  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }

  if (btn) {
    btn.innerHTML = '&#x2705; Скопировано (' + tasks.length + ')';
    setTimeout(function() { btn.innerHTML = origHTML; }, 2000);
  }
  showNotification('Скопировано ' + tasks.length + (tasks.length === 1 ? ' задача' : ' задач'), 'success');
}

/* --- Task modal --- */
function openTaskModal(taskId) {
  editingTaskId = taskId || null;
  currentTags = [];

  var modal = document.getElementById('task-modal');
  var title = document.getElementById('task-modal-title');

  if (editingTaskId) {
    title.textContent = 'Редактировать задачу';
    var task = findTaskById(editingTaskId);
    if (task) {
      document.getElementById('task-title').value = task.title || '';
      document.getElementById('task-desc').value = task.description || '';
      document.getElementById('task-desc-plain').value = task.description_plain || '';
      document.getElementById('task-status').value = task.status || 'backlog';
      document.getElementById('task-source').value = task.source || 'manual';
      document.getElementById('task-source-ref').value = task.source_ref || '';
      currentTags = [].concat(task.tags || []);
    }
  } else {
    title.textContent = 'Новая задача';
    document.getElementById('task-title').value = '';
    document.getElementById('task-desc').value = '';
    document.getElementById('task-desc-plain').value = '';
    document.getElementById('task-status').value = 'backlog';
    document.getElementById('task-source').value = 'manual';
    document.getElementById('task-source-ref').value = '';
  }

  renderTags();
  modal.style.display = 'flex';
  document.getElementById('task-title').focus();
}

function closeTaskModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('task-modal').style.display = 'none';
  editingTaskId = null;
}

function editTask(id) { openTaskModal(id); }

function findTaskById(id) {
  var statuses = ['backlog', 'in_progress', 'done'];
  for (var i = 0; i < statuses.length; i++) {
    var arr = tasksData[statuses[i]] || [];
    for (var j = 0; j < arr.length; j++) {
      if (arr[j].id === id) return arr[j];
    }
  }
  return null;
}

function addTag(tag) {
  if (!tag || currentTags.indexOf(tag) !== -1) return;
  currentTags.push(tag);
  renderTags();
}

function removeTag(tag) {
  currentTags = currentTags.filter(function(t) { return t !== tag; });
  renderTags();
}

function renderTags() {
  var list = document.getElementById('task-tags-list');
  list.innerHTML = currentTags.map(function(t) {
    return '<span class="tag-chip"><span class="task-tag ' + escHtml(t) + '">'
      + escHtml(t) + '</span><button onclick="removeTag(\'' + escHtml(t) + '\')" type="button">\u2715</button></span>';
  }).join('');
}

async function saveTask() {
  var title = document.getElementById('task-title').value.trim();
  if (!title) { showNotification('Введите название задачи', 'error'); return; }

  var data = {
    title: title,
    description: document.getElementById('task-desc').value.trim() || null,
    description_plain: document.getElementById('task-desc-plain').value.trim() || null,
    status: document.getElementById('task-status').value,
    source: document.getElementById('task-source').value,
    source_ref: document.getElementById('task-source-ref').value.trim() || null,
    tags: currentTags,
  };

  try {
    if (editingTaskId) {
      await api('PATCH', '/api/admin/tasks/' + editingTaskId, data);
      showNotification('Задача обновлена', 'success');
    } else {
      await api('POST', '/api/admin/tasks', data);
      showNotification('Задача создана', 'success');
    }
    closeTaskModal();
    await loadTasks();
  } catch (err) {
    console.error('Save task failed', err);
    showNotification('Ошибка сохранения', 'error');
  }
}

/* --- Delete modal --- */
function promptDeleteTask(id, title) {
  deletingTaskId = id;
  document.getElementById('delete-task-name').textContent = '\u00AB' + title + '\u00BB';
  document.getElementById('task-delete-modal').style.display = 'flex';
}

function closeDeleteModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('task-delete-modal').style.display = 'none';
  deletingTaskId = null;
}

async function confirmDeleteTask() {
  if (!deletingTaskId) return;
  try {
    await api('DELETE', '/api/admin/tasks/' + deletingTaskId);
    showNotification('Задача удалена', 'success');
    closeDeleteModal();
    await loadTasks();
  } catch (err) {
    console.error('Delete failed', err);
    showNotification('Ошибка удаления', 'error');
  }
}

/* ═══════════════════════════════════════════════════
   TASK VIEW
═══════════════════════════════════════════════════ */
function viewTask(id) {
  var task = findTaskById(id);
  if (!task) return;
  viewingTaskId = id;

  var statusLabels = { backlog: '📋 Backlog', in_progress: '🔄 В работе', done: '✅ Готово' };
  var sourceLabels = { manual: 'Manual', git_commit: 'Git commit', ai_generated: 'AI generated', github_issue: 'GitHub issue' };

  document.getElementById('tv-title').textContent = task.title;

  var statusEl = document.getElementById('tv-status');
  statusEl.textContent = statusLabels[task.status] || task.status;
  statusEl.className = 'tv-badge ' + (task.status || '');

  document.getElementById('tv-source').textContent = sourceLabels[task.source] || task.source || '—';

  document.getElementById('tv-created').textContent = task.created_at
    ? new Date(task.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';
  document.getElementById('tv-updated').textContent = task.updated_at
    ? new Date(task.updated_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';

  var descSection = document.getElementById('tv-desc-section');
  var descEl = document.getElementById('tv-desc');
  if (task.description) {
    descSection.style.display = 'block';
    descEl.innerHTML = formatTaskDescription(task.description);
  } else {
    descSection.style.display = 'none';
  }

  var plainSection = document.getElementById('tv-plain-section');
  var plainEl = document.getElementById('tv-plain');
  if (task.description_plain && task.description_plain !== task.description) {
    plainSection.style.display = 'block';
    plainEl.textContent = task.description_plain;
  } else {
    plainSection.style.display = 'none';
  }

  var tagsSection = document.getElementById('tv-tags-section');
  var tagsEl = document.getElementById('tv-tags');
  if (task.tags && task.tags.length) {
    tagsSection.style.display = 'block';
    tagsEl.innerHTML = task.tags.map(function(t) {
      return '<span class="task-tag ' + escHtml(t) + '">' + escHtml(t) + '</span>';
    }).join('');
  } else {
    tagsSection.style.display = 'none';
  }

  var refSection = document.getElementById('tv-ref-section');
  var refEl = document.getElementById('tv-ref');
  if (task.source_ref) {
    refSection.style.display = 'block';
    refEl.textContent = task.source_ref;
  } else {
    refSection.style.display = 'none';
  }

  document.getElementById('tv-edit-btn').onclick = function() {
    closeViewModal();
    editTask(id);
  };

  document.getElementById('tv-delete-btn').onclick = function() {
    closeViewModal();
    promptDeleteTask(id, task.title);
  };

  document.getElementById('task-view-modal').style.display = 'flex';
}

function formatTaskDescription(text) {
  var safe = escHtml(text);
  safe = safe.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  safe = safe.replace(/\n/g, '<br>');
  return safe;
}

function closeViewModal(event) {
  if (event && event.target !== event.currentTarget) return;
  document.getElementById('task-view-modal').style.display = 'none';
  viewingTaskId = null;
}

async function copyTaskToClipboard() {
  var task = findTaskById(viewingTaskId);
  if (!task) return;

  var statusLabels = { backlog: 'Backlog', in_progress: 'В работе', done: 'Готово' };
  var sourceLabels = { manual: 'Manual', git_commit: 'Git commit', ai_generated: 'AI generated', github_issue: 'GitHub issue' };

  var text = '# ' + task.title + '\n\n';
  text += 'Статус: ' + (statusLabels[task.status] || task.status) + '\n';
  text += 'Источник: ' + (sourceLabels[task.source] || task.source || 'manual') + '\n';
  if (task.tags && task.tags.length) text += 'Теги: ' + task.tags.join(', ') + '\n';
  if (task.created_at) text += 'Создана: ' + new Date(task.created_at).toLocaleString('ru-RU') + '\n';
  text += '\n';

  if (task.description) text += '## Техническое описание\n\n' + task.description + '\n\n';
  if (task.description_plain && task.description_plain !== task.description) {
    text += '## Описание простым языком\n\n' + task.description_plain + '\n\n';
  }
  if (task.source_ref) text += '## Источник\n' + task.source_ref + '\n';

  var btn = document.getElementById('btn-copy-task');
  var origHTML = btn.innerHTML;

  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }

  btn.innerHTML = '&#x2705; Скопировано!';
  btn.classList.add('copied');
  setTimeout(function() {
    btn.innerHTML = origHTML;
    btn.classList.remove('copied');
  }, 2000);
}

/* ═══════════════════════════════════════════════════
   EVENT LISTENERS (registered after DOM ready)
═══════════════════════════════════════════════════ */

/* Keyboard shortcuts */
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    // First clear selection if any
    if (selectedTaskIds.size > 0) {
      clearSelection();
      return;
    }
    closeViewModal();
    closeTaskModal();
    closeDeleteModal();
    return;
  }

  // Only on tasks page
  if (typeof getCurrentPage === 'function' && getCurrentPage() !== 'tasks') return;

  // Ctrl/Cmd + A — select all
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
    e.preventDefault();
    selectAllTasks();
    return;
  }

  // Ctrl/Cmd + C — copy selected (only if no text is selected on page)
  if ((e.ctrlKey || e.metaKey) && e.key === 'c' && selectedTaskIds.size > 0) {
    var sel = window.getSelection ? window.getSelection().toString() : '';
    if (!sel) {
      e.preventDefault();
      copySelectedTasks();
    }
  }
});

/* Kanban card action delegation (select / view / edit / delete) */
document.querySelector('.kanban-board').addEventListener('click', function(e) {
  var deleteBtn = e.target.closest('.task-delete-btn');
  if (deleteBtn) {
    promptDeleteTask(deleteBtn.dataset.id, deleteBtn.dataset.title);
    return;
  }
  var editBtn = e.target.closest('.task-edit-btn');
  if (editBtn) {
    editTask(editBtn.dataset.id);
    return;
  }
  var card = e.target.closest('.task-card');
  if (card) {
    var taskId = card.dataset.id;
    // Select mode OR Ctrl/Cmd+click → toggle selection
    if (selectMode || e.ctrlKey || e.metaKey) {
      e.preventDefault();
      toggleTaskSelection(taskId, card);
      return;
    }
    // Normal click → view
    viewTask(taskId);
  }
});
