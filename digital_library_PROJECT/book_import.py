# book_import.py
import requests
import csv
import os
from flask import (
    Blueprint, render_template, request, redirect, 
    url_for, flash, current_app, jsonify
)
from werkzeug.utils import secure_filename
from models import Book, Category
from extensions import db
from datetime import datetime
import uuid
import time

book_import = Blueprint('book_import', __name__)

@book_import.route('/admin/import_books', methods=['GET'])
def import_books_page():
    categories = Category.query.all()
    return render_template('admin/import_books.html', categories=categories)

@book_import.route('/admin/import_from_google', methods=['POST'])
def import_from_google():
    # Nhận tham số từ form
    search_term = request.form.get('search_term', '')
    category_id = request.form.get('category_id')
    max_results = request.form.get('max_results', 10, type=int)
    
    if not search_term:
        flash('Vui lòng nhập từ khóa tìm kiếm!', 'danger')
        return redirect(url_for('book_import.import_books_page'))
    
    # Gọi API Google Books
    response = requests.get(
        f"https://www.googleapis.com/books/v1/volumes",
        params={
            "q": search_term,
            "maxResults": max_results
        }
    )
    
    if response.status_code != 200:
        flash('Có lỗi khi kết nối đến Google Books API!', 'danger')
        return redirect(url_for('book_import.import_books_page'))
    
    books_data = response.json()
    
    if 'items' not in books_data or not books_data['items']:
        flash('Không tìm thấy sách nào phù hợp!', 'warning')
        return redirect(url_for('book_import.import_books_page'))
    
    # Lưu thông tin sách vào database
    added_count = 0
    for item in books_data['items']:
        volume_info = item.get('volumeInfo', {})
        
        # Lấy thông tin cơ bản
        title = volume_info.get('title', 'Không có tiêu đề')
        authors = volume_info.get('authors', ['Không rõ tác giả'])
        author = ', '.join(authors)
        publication_year = None
        published_date = volume_info.get('publishedDate')
        if published_date and len(published_date) >= 4:
            try:
                publication_year = int(published_date[:4])
            except ValueError:
                pass
        
        description = volume_info.get('description', '')
        page_count = volume_info.get('pageCount')
        language = volume_info.get('language', 'en')
        
        # Kiểm tra sách đã tồn tại chưa
        existing_book = Book.query.filter_by(title=title, author=author).first()
        if existing_book:
            continue
        
        # Tạo sách mới
        book = Book(
            title=title,
            author=author,
            category_id=category_id,
            description=description,
            publication_year=publication_year,
            language=language,
            pages=page_count,
            is_available=True,
            added_by=request.cookies.get('user_id')
        )
        
        # Lấy và lưu ảnh bìa nếu có
        if 'imageLinks' in volume_info and 'thumbnail' in volume_info['imageLinks']:
            try:
                image_url = volume_info['imageLinks']['thumbnail']
                image_response = requests.get(image_url)
                if image_response.status_code == 200:
                    filename = f"{uuid.uuid4()}.jpg"
                    image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'covers', filename)
                    with open(image_path, 'wb') as f:
                        f.write(image_response.content)
                    book.cover_image = filename
            except Exception as e:
                print(f"Lỗi khi tải ảnh bìa: {e}")
        
        # Lưu vào database
        try:
            db.session.add(book)
            db.session.commit()
            added_count += 1
        except Exception as e:
            db.session.rollback()
            print(f"Lỗi khi thêm sách: {e}")
    
    if added_count > 0:
        flash(f'Đã nhập {added_count} sách thành công!', 'success')
    else:
        flash('Không có sách nào được thêm mới.', 'info')
        
    return redirect(url_for('book_import.import_books_page'))

@book_import.route('/admin/import_from_csv', methods=['POST'])
def import_from_csv():
    if 'csv_file' not in request.files:
        flash('Không tìm thấy file!', 'danger')
        return redirect(url_for('book_import.import_books_page'))
    
    file = request.files['csv_file']
    if file.filename == '':
        flash('Không có file nào được chọn!', 'danger')
        return redirect(url_for('book_import.import_books_page'))
    
    if not file.filename.endswith('.csv'):
        flash('File phải có định dạng CSV!', 'danger')
        return redirect(url_for('book_import.import_books_page'))
    
    # Lưu file tạm để xử lý
    temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', secure_filename(file.filename))
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    file.save(temp_path)
    
    added_count = 0
    error_count = 0
    
    try:
        with open(temp_path, 'r', encoding='utf-8-sig') as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                # Kiểm tra các trường bắt buộc
                if not row.get('title') or not row.get('author'):
                    error_count += 1
                    continue
                
                # Kiểm tra sách đã tồn tại chưa
                existing_book = Book.query.filter_by(
                    title=row.get('title'), 
                    author=row.get('author')
                ).first()
                
                if existing_book:
                    error_count += 1
                    continue
                
                # Chuyển đổi category_name thành category_id nếu có
                category_id = None
                if row.get('category'):
                    category = Category.query.filter_by(name=row.get('category')).first()
                    if category:
                        category_id = category.id
                
                # Xử lý năm xuất bản
                publication_year = None
                if row.get('publication_year'):
                    try:
                        publication_year = int(row.get('publication_year'))
                    except ValueError:
                        pass
                
                # Xử lý số trang
                pages = None
                if row.get('pages'):
                    try:
                        pages = int(row.get('pages'))
                    except ValueError:
                        pass
                
                # Tạo sách mới
                book = Book(
                    title=row.get('title'),
                    author=row.get('author'),
                    category_id=category_id,
                    description=row.get('description', ''),
                    publication_year=publication_year,
                    language=row.get('language', ''),
                    pages=pages,
                    is_available=True,
                    added_by=request.cookies.get('user_id')
                )
                
                # Lưu vào database
                try:
                    db.session.add(book)
                    db.session.commit()
                    added_count += 1
                except Exception as e:
                    db.session.rollback()
                    error_count += 1
                    print(f"Lỗi khi thêm sách: {e}")
        
        flash(f'Đã nhập {added_count} sách thành công, {error_count} sách lỗi!', 'success')
        
    except Exception as e:
        flash(f'Có lỗi xảy ra khi xử lý file CSV: {e}', 'danger')
    
    # Xóa file tạm
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    return redirect(url_for('book_import.import_books_page'))

@book_import.route('/admin/import_books/export_template', methods=['GET'])
def export_csv_template():
    from io import StringIO
    import csv
    
    # Tạo file CSV mẫu
    csv_output = StringIO()
    fieldnames = ['title', 'author', 'category', 'description', 'publication_year', 'language', 'pages']
    writer = csv.DictWriter(csv_output, fieldnames=fieldnames)
    writer.writeheader()
    
    # Thêm một số dòng mẫu
    writer.writerow({
        'title': 'Tên sách mẫu 1',
        'author': 'Tác giả mẫu',
        'category': 'Lập trình',
        'description': 'Mô tả về sách',
        'publication_year': '2022',
        'language': 'Tiếng Việt',
        'pages': '200'
    })
    
    writer.writerow({
        'title': 'Tên sách mẫu 2',
        'author': 'Tác giả khác',
        'category': 'AI & Machine Learning',
        'description': 'Một mô tả khác',
        'publication_year': '2021',
        'language': 'Tiếng Anh',
        'pages': '350'
    })
    
    from flask import Response
    output = csv_output.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=template_import_sach.csv"}
    )