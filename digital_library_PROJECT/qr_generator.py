# qr_generator.py
import qrcode
import os
from flask import current_app, url_for

def generate_book_qr(book_id, host_url=None):
    """
    Tạo mã QR cho sách dựa trên ID
    
    Parameters:
    book_id (int): ID của sách
    host_url (str): URL của trang web, mặc định là None (sẽ sử dụng url_for)
    
    Returns:
    str: Tên file mã QR
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # Tạo URL cho mã QR
    if host_url:
        qr_data = f"{host_url}/books/borrow/{book_id}"
    else:
        # Sử dụng URL tương đối
        qr_data = f"/books/borrow/{book_id}"
    
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Tạo tên file và đường dẫn
    filename = f"qr_book_{book_id}.png"
    qr_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'qrcodes')
    
    # Đảm bảo thư mục tồn tại
    os.makedirs(qr_folder, exist_ok=True)
    
    qr_path = os.path.join(qr_folder, filename)
    
    # Lưu hình ảnh
    img.save(qr_path)
    
    return filename

def generate_user_qr(user_id, host_url=None):
    """
    Tạo mã QR cho người dùng dựa trên ID
    
    Parameters:
    user_id (int): ID của người dùng
    host_url (str): URL của trang web, mặc định là None
    
    Returns:
    str: Tên file mã QR
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # Tạo URL cho mã QR
    if host_url:
        qr_data = f"{host_url}/user/{user_id}/qr"
    else:
        # Sử dụng URL tương đối
        qr_data = f"/user/{user_id}/qr"
    
    qr.add_data(qr_data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Tạo tên file và đường dẫn
    filename = f"qr_user_{user_id}.png"
    qr_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'qrcodes')
    
    # Đảm bảo thư mục tồn tại
    os.makedirs(qr_folder, exist_ok=True)
    
    qr_path = os.path.join(qr_folder, filename)
    
    # Lưu hình ảnh
    img.save(qr_path)
    
    return filename