/**
 * Register Page JavaScript
 * 注册页面专用JavaScript
 */

// Use a safer initialization approach
(function() {
  'use strict';

  // Wait for DOM to be fully loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function init() {
    try {
      setupFloatingLabels();
      setupFormValidation();
    } catch (error) {
      console.warn('Register page initialization error:', error);
    }
  }

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

  function setupFormValidation() {
    const form = document.querySelector('form[action="/register"]');
    if (!form) return;

    form.addEventListener('submit', function(e) {
      const emailInput = form.querySelector('input[name="email"]');
      const passwordInput = form.querySelector('input[name="password"]');
      const confirmPasswordInput = form.querySelector('input[name="confirm_password"]');

      // Basic validation
      if (emailInput && !emailInput.value.trim()) {
        e.preventDefault();
        showFormError('请输入邮箱地址');
        emailInput.focus();
        return;
      }

      if (passwordInput && !passwordInput.value.trim()) {
        e.preventDefault();
        showFormError('请输入密码');
        passwordInput.focus();
        return;
      }

      if (passwordInput && passwordInput.value.length < 6) {
        e.preventDefault();
        showFormError('密码长度至少需要6个字符');
        passwordInput.focus();
        return;
      }

      if (confirmPasswordInput && passwordInput && confirmPasswordInput.value !== passwordInput.value) {
        e.preventDefault();
        showFormError('两次输入的密码不一致');
        confirmPasswordInput.focus();
        return;
      }

      // Show loading state
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.innerHTML = '⏳ 注册中...';
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
    const form = document.querySelector('form[action="/register"]');
    if (form) {
      form.parentNode.insertBefore(errorDiv, form.nextSibling);
    }
  }
})();
