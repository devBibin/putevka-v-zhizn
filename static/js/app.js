function showAlert(message, type = 'danger') {
  const alert = document.createElement('div');
  alert.className = `alert alert-${type} alert-dismissible fade show position-fixed bottom-0 end-0 m-3`;
  alert.role = 'alert';
  alert.innerHTML = `${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
  document.body.appendChild(alert);
  setTimeout(() => alert.remove(), 5000);
}
