// Auto-close alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function() {
    // Auto-đóng thông báo sau 5 giây
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-important)');
        alerts.forEach(function(alert) {
            try {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {
                console.error("Lỗi khi đóng alert:", e);
            }
        });
    }, 5000);
    
    // Không xử lý modal ở đây nữa, logic đã được chuyển vào từng trang riêng biệt
});