/**
 * Home Page JavaScript
 * 首页专用JavaScript
 */

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
  // Setup floating labels for forms
  setupFloatingLabels();

  // Setup form submission for text processing
  setupTextProcessingForm();
});

function setupFloatingLabels() {
  // Floating label support
  function refreshFloating() {
    document.querySelectorAll('.input-group').forEach(group => {
      const field = group.querySelector('input, textarea, select');
      const label = group.querySelector('label');
      if (!field || !label) return;
      if (field.value && field.value.trim() !== '') {
        label.classList.add('force-float');
      } else {
        label.classList.remove('force-float');
      }
    });
  }

  document.addEventListener('input', e => {
    if (e.target.matches('.input-group input, .input-group textarea, .input-group select')) {
      refreshFloating();
    }
  });

  // Initial check
  refreshFloating();
}

function setupTextProcessingForm() {
  const form = document.querySelector('form[action="/process_text"]');
  if (!form) return;

  form.addEventListener('submit', function(e) {
    const textarea = form.querySelector('textarea[name="text"]');

    // Basic validation
    if (textarea && !textarea.value.trim()) {
      e.preventDefault();
      showFormError('请输入要处理的文本');
      textarea.focus();
      return;
    }

    // Show loading state
    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.innerHTML = '⏳ 处理中...';
      submitBtn.disabled = true;
    }
  });
}

function showFormError(message) {
  // Remove existing error messages
  const existingError = document.querySelector('.form-error');
  if (existingError) {
    existingError.remove();
  }

  // Create new error message
  const errorDiv = document.createElement('div');
  errorDiv.className = 'form-error';
  errorDiv.style.cssText = 'color: #e74c3c; margin: 10px 0; padding: 8px; background: #fdf2f2; border: 1px solid #fecaca; border-radius: 4px;';
  errorDiv.textContent = message;

  // Insert after the form
  const form = document.querySelector('form[action="/process_text"]');
  if (form) {
    form.parentNode.insertBefore(errorDiv, form.nextSibling);
  }
}
