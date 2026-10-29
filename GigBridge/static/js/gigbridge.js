/* GigBridge Master JavaScript */

document.addEventListener('DOMContentLoaded', () => {

  /* ─── 1. Navbar scroll effect ─── */
  const navbar = document.getElementById('mainNavbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 20) {
        navbar.classList.add('scrolled');
        navbar.style.boxShadow = '0 4px 20px rgba(0,0,0,.3)';
      } else {
        navbar.classList.remove('scrolled');
        navbar.style.boxShadow = '';
      }
    }, { passive: true });
  }

  /* ─── 2. Auto-dismiss alerts ─── */
  document.querySelectorAll('.alert.alert-dismissible').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 6000);
  });

  /* ─── 3. Dashboard sidebar mobile toggle ─── */
  const sidebar = document.querySelector('.dashboard-sidebar');
  const toggleBtn = document.getElementById('sidebarToggle');
  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('show');
    });
    // Close on backdrop click
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('show') &&
          !sidebar.contains(e.target) &&
          !toggleBtn.contains(e.target)) {
        sidebar.classList.remove('show');
      }
    });
  }

  /* ─── 4. Star rating interactive picker ─── */
  const ratingSelect = document.querySelector('select[name="rating"]');
  const starContainer = document.getElementById('starPicker');
  if (ratingSelect && starContainer) {
    renderStars(parseInt(ratingSelect.value) || 5);
    starContainer.querySelectorAll('.star-pick').forEach(star => {
      star.addEventListener('click', () => {
        const val = parseInt(star.dataset.value);
        ratingSelect.value = val;
        renderStars(val);
      });
      star.addEventListener('mouseenter', () => renderStars(parseInt(star.dataset.value)));
    });
    starContainer.addEventListener('mouseleave', () => renderStars(parseInt(ratingSelect.value)));

    function renderStars(val) {
      starContainer.querySelectorAll('.star-pick').forEach((s, i) => {
        s.classList.toggle('active', i < val);
      });
    }
  }

  /* ─── 5. Skills tag input ─── */
  const skillsInput = document.querySelector('input[name="required_skills"]');
  if (skillsInput) {
    skillsInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') e.preventDefault();
    });
  }

  /* ─── 6. Message chat – scroll to bottom ─── */
  const chatContainer = document.getElementById('chatMessages');
  if (chatContainer) {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  /* ─── 7. AJAX message submit ─── */
  const msgForm = document.getElementById('messageForm');
  if (msgForm) {
    msgForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(msgForm);
      try {
        const res = await fetch(msgForm.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: fd,
        });
        if (res.ok) {
          const data = await res.json();
          if (data.status === 'ok') {
            appendMessage(data.message, data.time);
            msgForm.querySelector('textarea').value = '';
            chatContainer && (chatContainer.scrollTop = chatContainer.scrollHeight);
          }
        }
      } catch (err) {
        msgForm.submit(); // fallback
      }
    });
  }

  function appendMessage(text, time) {
    if (!chatContainer) return;
    const div = document.createElement('div');
    div.className = 'd-flex justify-content-end mb-3';
    div.innerHTML = `
      <div>
        <div class="message-bubble sent">${escapeHtml(text)}</div>
        <div class="text-muted small text-end mt-1">${time}</div>
      </div>`;
    chatContainer.appendChild(div);
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /* ─── 8. Animate on scroll ─── */
  const animEls = document.querySelectorAll('[data-animate]');
  if (animEls.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('fade-in-up');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });
    animEls.forEach(el => observer.observe(el));
  }

  /* ─── 9. Counter animation for stats ─── */
  document.querySelectorAll('[data-counter]').forEach(el => {
    const target = parseInt(el.dataset.counter);
    let start = 0;
    const duration = 1800;
    const step = target / (duration / 16);
    const timer = setInterval(() => {
      start = Math.min(start + step, target);
      el.textContent = Math.floor(start).toLocaleString();
      if (start >= target) clearInterval(timer);
    }, 16);
  });

  /* ─── 10. Tooltip init ─── */
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover' });
  });

  /* ─── 11. Budget type toggle ─── */
  const budgetTypeSelect = document.querySelector('select[name="budget_type"]');
  const budgetRangeRow = document.getElementById('budgetRangeRow');
  if (budgetTypeSelect && budgetRangeRow) {
    const toggle = () => {
      budgetRangeRow.style.display = budgetTypeSelect.value === 'hourly' ? '' : '';
    };
    toggle();
    budgetTypeSelect.addEventListener('change', toggle);
  }

});
