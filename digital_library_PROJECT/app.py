from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import uuid
import time
import logging
from logging.handlers import RotatingFileHandler
import traceback

# Import db từ extensions
from extensions import db

# Tạo ứng dụng Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_completely_new_secret_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {'timeout': 30}  # Tăng timeout lên 30 giây
}
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
app.config['DEBUG'] = True

# In đường dẫn database để kiểm tra
print("Database path:", os.path.join(app.root_path, 'library.db'))

# Đảm bảo thư mục uploads tồn tại
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'books'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'covers'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'temp'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes'), exist_ok=True)

# Khởi tạo db với app
db.init_app(app)

# Import models sau khi khởi tạo db
from models import User, Book, Borrow, Category
from qr_generator import generate_book_qr, generate_user_qr

# Import và đăng ký blueprints
from book_import import book_import
from analytics import analytics

# Đăng ký blueprints
app.register_blueprint(book_import)
app.register_blueprint(analytics)

# Thêm xử lý lỗi toàn cục
@app.errorhandler(Exception)
def handle_exception(e):
    # In lỗi ra console
    print(f"Unhandled exception: {str(e)}")
    traceback.print_exc()
    
    # Hiển thị cho người dùng
    flash(f'Lỗi hệ thống: {str(e)}', 'danger')
    try:
        return render_template('error.html', error=str(e)), 500
    except:
        # Fallback nếu không tìm thấy template error.html
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Lỗi hệ thống</title></head>
        <body>
            <h1>Đã xảy ra lỗi</h1>
            <p>{str(e)}</p>
            <a href="/">Quay về trang chủ</a>
        </body>
        </html>
        """, 500

# Thêm filter xử lý ngày tháng an toàn
@app.template_filter('safe_date')
def safe_date(date_value, format='%d/%m/%Y'):
    """Filter để hiển thị ngày tháng an toàn trong template"""
    if date_value is None:
        return "N/A"
        
    if isinstance(date_value, str):
        return date_value
        
    try:
        return date_value.strftime(format)
    except:
        return str(date_value)

# Hàm tiện ích xử lý ngày tháng
def ensure_datetime(date_value):
    """Đảm bảo giá trị trả về là đối tượng datetime hợp lệ"""
    if date_value is None:
        return None
    
    if isinstance(date_value, datetime):
        return date_value
    
    # Nếu là chuỗi, thử chuyển đổi sang datetime
    if isinstance(date_value, str):
        try:
            return datetime.fromisoformat(date_value)
        except ValueError:
            # Thử với các định dạng khác
            try:
                return datetime.strptime(date_value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    return datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError:
                    pass
    
    # Trả về mặc định nếu không thể chuyển đổi
    return datetime.utcnow()

# Kiểm tra đăng nhập
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để truy cập trang này!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Kiểm tra admin
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Vui lòng đăng nhập để truy cập trang này!', 'danger')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Bạn không có quyền truy cập trang này!', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.context_processor
def inject_user():
    user = None
    categories = []
    qr_urls = {}
    
    # Lấy thông tin người dùng hiện tại
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            qr_urls['user_qr_url'] = url_for('user_qr', user_id=user.id)
    
    # Lấy danh sách danh mục cho dropdown menu
    try:
        categories = Category.query.all()
    except:
        pass
    
    # Thêm URL cho tính năng quét QR
    qr_urls['scan_qr_url'] = url_for('scan_qr')
        
    return dict(
        current_user=user,
        categories=categories,
        qr_urls=qr_urls
    )

# Routes
@app.route('/')
def index():
    books = Book.query.order_by(Book.added_at.desc()).limit(6).all()
    return render_template('index.html', books=books)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                              'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/login', methods=['GET', 'POST'])
def login():
    print("Login route accessed")
    
    if 'user_id' in session:
        print("User already in session:", session['user_id'])
        user = User.query.get(session['user_id'])
        if user and user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        
        print(f"Login attempt: username='{username}', password='{password}'")
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            print(f"User found: {user.username}, role={user.role}")
            print(f"Stored password: '{user.password}'")
            print(f"Input password: '{password}'")
            print(f"Password match: {user.password == password}")
        else:
            print(f"No user found with username: {username}")
            
        if user and user.password == password:  # Sử dụng so sánh trực tiếp
            # Lưu thông tin vào session
            session.clear()  # Xóa session cũ
            session['user_id'] = user.id
            print(f"Login successful. Session user_id: {session['user_id']}")
            
            flash('Đăng nhập thành công!', 'success')
            
            # Chuyển hướng tùy theo role
            if user.role == 'admin':
                print("Redirecting to admin dashboard")
                return redirect(url_for('admin_dashboard'))
            
            print("Redirecting to index")
            return redirect(url_for('index'))
        else:
            print("Login failed")
            flash('Tên đăng nhập hoặc mật khẩu không đúng!', 'danger')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        full_name = request.form['full_name']
        
        # Kiểm tra username đã tồn tại chưa
        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập đã tồn tại!', 'danger')
            return render_template('register.html')
        
        # Kiểm tra email đã tồn tại chưa
        if User.query.filter_by(email=email).first():
            flash('Email đã được sử dụng!', 'danger')
            return render_template('register.html')
        
        # Tạo người dùng mới
        new_user = User(
            username=username,
            password=password,  # Lưu trực tiếp mật khẩu
            email=email,
            full_name=full_name,
            role='user',
            created_at=datetime.utcnow()  # Đảm bảo created_at là đối tượng datetime
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(f"Error registering user: {e}")
            flash('Có lỗi xảy ra khi đăng ký. Vui lòng thử lại sau.', 'danger')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Đã đăng xuất thành công!', 'success')
    return redirect(url_for('index'))

@app.route('/books')
def book_list():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category_id = request.args.get('category', type=int)
    
    query = Book.query
    
    if search:
        query = query.filter(Book.title.contains(search) | Book.author.contains(search))
    
    if category_id:
        query = query.filter(Book.category_id == category_id)
    
    # Xử lý tất cả các sách để đảm bảo added_at là đối tượng datetime hợp lệ
    try:
        all_books = query.all()
        print(f"Found {len(all_books)} books in database")
        for book in all_books:
            # Đảm bảo added_at là đối tượng datetime
            if hasattr(book, 'added_at'):
                book.added_at = ensure_datetime(book.added_at)
            else:
                book.added_at = datetime.utcnow()
                
            # Đảm bảo category_info
            if hasattr(book, 'category_id') and book.category_id and (not hasattr(book, 'category_info') or book.category_info is None):
                try:
                    book.category_info = Category.query.get(book.category_id)
                except:
                    book.category_info = None
    except Exception as e:
        print(f"Error processing books: {e}")
    
    books = query.paginate(page=page, per_page=12)
    categories = Category.query.all()
    
    return render_template('book/list.html', books=books, categories=categories, current_category=category_id)

@app.route('/books/<int:book_id>')
def book_detail(book_id):
    try:
        book = Book.query.get_or_404(book_id)
        borrowed_count = 0
        
        # Xử lý và đảm bảo các thuộc tính của book
        # 1. Xử lý added_at an toàn
        try:
            if hasattr(book, 'added_at') and book.added_at:
                if isinstance(book.added_at, str):
                    book.added_at = datetime.strptime(book.added_at, "%Y-%m-%d %H:%M:%S")
                elif not isinstance(book.added_at, datetime):
                    book.added_at = datetime.utcnow()
            else:
                book.added_at = datetime.utcnow()
        except Exception as e:
            print(f"Lỗi xử lý ngày added_at: {e}")
            book.added_at = datetime.utcnow()
        
        # 2. Đếm số lượt mượn an toàn
        try:
            borrowed_count = Borrow.query.filter_by(book_id=book.id).count()
        except Exception as e:
            print(f"Lỗi đếm số lượt mượn: {e}")
            borrowed_count = 0
        
        # 3. Đảm bảo có category_info
        try:
            if not hasattr(book, 'category_info') or book.category_info is None:
                if hasattr(book, 'category_id') and book.category_id:
                    book.category_info = Category.query.get(book.category_id)
        except Exception as e:
            print(f"Lỗi lấy thông tin danh mục: {e}")
        
        # 4. Xử lý thông tin mượn của user hiện tại nếu đã đăng nhập
        active_borrow = None
        if 'user_id' in session:
            try:
                # Lấy thông tin mượn sách hiện tại của user cho cuốn sách này
                active_borrow = Borrow.query.filter_by(
                    user_id=session['user_id'], 
                    book_id=book.id,
                    status='borrowed'
                ).first()
                
                # Xử lý ngày tháng nếu có thông tin mượn
                if active_borrow:
                    if hasattr(active_borrow, 'borrow_date') and active_borrow.borrow_date:
                        if isinstance(active_borrow.borrow_date, str):
                            active_borrow.borrow_date = datetime.strptime(active_borrow.borrow_date, "%Y-%m-%d %H:%M:%S")
                    
                    if hasattr(active_borrow, 'due_date') and active_borrow.due_date:
                        if isinstance(active_borrow.due_date, str):
                            active_borrow.due_date = datetime.strptime(active_borrow.due_date, "%Y-%m-%d %H:%M:%S")
                    
                    if hasattr(active_borrow, 'return_date') and active_borrow.return_date:
                        if isinstance(active_borrow.return_date, str):
                            active_borrow.return_date = datetime.strptime(active_borrow.return_date, "%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"Lỗi xử lý thông tin mượn sách: {e}")
        
        # Truyền dữ liệu đã được xử lý an toàn vào template
        return render_template(
            'book/detail.html', 
            book=book, 
            borrowed_count=borrowed_count,
            active_borrow=active_borrow
        )
    except Exception as e:
        print(f"Error querying book details: {e}")
        traceback.print_exc()  # In ra traceback chi tiết để debug
        flash('Có lỗi khi tải thông tin sách', 'danger')
        return redirect(url_for('book_list'))

@app.route('/user/profile')
@login_required
def user_profile():
    user = User.query.get(session['user_id'])
    
    # Xử lý ngày đăng ký của user
    if hasattr(user, 'created_at'):
        user.created_at = ensure_datetime(user.created_at)
    
    # Lấy danh sách mượn sách và xử lý ngày tháng
    try:
        borrows = Borrow.query.filter_by(user_id=user.id).order_by(Borrow.borrow_date.desc()).all()
        for borrow in borrows:
            borrow.borrow_date = ensure_datetime(borrow.borrow_date)
            borrow.due_date = ensure_datetime(borrow.due_date)
            borrow.return_date = ensure_datetime(borrow.return_date)
    except Exception as e:
        print(f"Error fetching borrows: {e}")
        borrows = []
    
    return render_template('user/profile.html', user=user, borrows=borrows)

@app.route('/user/borrows')
@login_required
def user_borrows():
    user_id = session['user_id']
    
    try:
        # Sử dụng cú pháp SQL trực tiếp để tránh vấn đề với SQLAlchemy ORM
        borrows_data = db.session.execute(db.text('''
            SELECT b.id, b.borrow_date, b.due_date, b.return_date, b.status,
                   bk.id as book_id, bk.title, bk.author
            FROM borrows b
            JOIN books bk ON b.book_id = bk.id
            WHERE b.user_id = :user_id
            ORDER BY b.borrow_date DESC
        '''), {'user_id': user_id}).fetchall()
        
        # Chuyển dữ liệu thành list tuple (borrow, book)
        borrows = []
        for row in borrows_data:
            borrow = {
                'id': row.id,
                'borrow_date': row.borrow_date,
                'due_date': row.due_date,
                'return_date': row.return_date,
                'status': row.status
            }
            book = {
                'id': row.book_id,
                'title': row.title,
                'author': row.author
            }
            borrows.append((borrow, book))
            
        print(f"Số lượt mượn tìm thấy: {len(borrows)}")
    except Exception as e:
        print(f"Error fetching user borrows: {e}")
        traceback.print_exc()
        borrows = []
        flash('Có lỗi khi tải danh sách mượn sách', 'danger')
    
    return render_template('user/borrows.html', borrows=borrows)

# Route cho trang quét QR
@app.route('/scan-qr')
@login_required
def scan_qr():
    return render_template('book/scan_qr.html')

# Route để hiển thị mã QR của sách
@app.route('/books/<int:book_id>/qr')
def book_qr(book_id):
    book = Book.query.get_or_404(book_id)
    
    # Kiểm tra nếu sách chưa có mã QR, tạo mới
    if not book.qr_code:
        try:
            host_url = request.host_url.rstrip('/')
            book.qr_code = generate_book_qr(book_id, host_url)
            db.session.commit()
        except Exception as e:
            print(f"Error generating QR code: {e}")
            db.session.rollback()
    
    # Trả về hình ảnh QR nếu có
    if book.qr_code:
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes'), book.qr_code)
    else:
        flash('Không thể tạo mã QR cho sách này!', 'danger')
        return redirect(url_for('book_detail', book_id=book_id))

# Route để hiển thị mã QR của người dùng
@app.route('/user/<int:user_id>/qr')
@login_required
def user_qr(user_id):
    # Chỉ cho phép admin hoặc chính người dùng đó xem mã QR của mình
    if user_id != session['user_id'] and User.query.get(session['user_id']).role != 'admin':
        flash('Bạn không có quyền xem mã QR này!', 'danger')
        return redirect(url_for('index'))
    
    # Tạo mã QR cho người dùng (không lưu vào db)
    try:
        host_url = request.host_url.rstrip('/')
        user_qr_file = generate_user_qr(user_id, host_url)
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes'), user_qr_file)
    except Exception as e:
        print(f"Error generating user QR code: {e}")
        flash('Không thể tạo mã QR!', 'danger')
        return redirect(url_for('user_profile'))

# Admin routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    total_books = Book.query.count()
    total_users = User.query.count()
    total_borrows = Borrow.query.count()
    
    # Sửa truy vấn để xử lý ngoại lệ và đảm bảo dữ liệu ngày tháng hợp lệ
    try:
        latest_borrows_data = db.session.query(
            Borrow, User, Book
        ).join(User, Borrow.user_id == User.id).join(Book, Borrow.book_id == Book.id).order_by(Borrow.borrow_date.desc()).limit(5).all()
        
        # Xử lý ngày tháng
        latest_borrows = []
        for borrow, user, book in latest_borrows_data:
            borrow.borrow_date = ensure_datetime(borrow.borrow_date)
            borrow.due_date = ensure_datetime(borrow.due_date)
            borrow.return_date = ensure_datetime(borrow.return_date)
            if hasattr(book, 'added_at'):
                book.added_at = ensure_datetime(book.added_at)
            latest_borrows.append((borrow, user, book))
    except Exception as e:
        print(f"Error querying latest borrows: {e}")
        latest_borrows = []  # Trả về danh sách trống nếu có lỗi
    
    return render_template('admin/dashboard.html', 
                          total_books=total_books,
                          total_users=total_users,
                          total_borrows=total_borrows,
                          latest_borrows=latest_borrows)

@app.route('/admin/books')
@admin_required
def admin_books():
    try:
        books = Book.query.all()
        # Xử lý ngày tháng
        for book in books:
            if hasattr(book, 'added_at'):
                book.added_at = ensure_datetime(book.added_at)
            else:
                book.added_at = datetime.utcnow()
    except Exception as e:
        print(f"Error querying books: {e}")
        books = []
        flash('Có lỗi khi tải danh sách sách', 'danger')
    
    return render_template('admin/books.html', books=books)

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        # Sử dụng truy vấn SQL trực tiếp an toàn hơn
        users_data = db.session.execute(db.text('''
            SELECT id, username, email, full_name, role, created_at
            FROM users
            ORDER BY id
        ''')).fetchall()
        
        # Chuyển đổi dữ liệu thành định dạng có thể sử dụng trong template
        users = []
        for user in users_data:
            users.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'created_at': user.created_at
            })
            
    except Exception as e:
        print(f"Error querying users: {e}")
        traceback.print_exc()
        users = []
        flash('Có lỗi khi tải danh sách người dùng', 'danger')
    
    return render_template('admin/users.html', users=users)

@app.route('/admin/borrows')
@admin_required
def admin_borrows():
    try:
        # Sử dụng truy vấn SQL trực tiếp
        borrows_data = db.session.execute(db.text('''
            SELECT b.id, b.borrow_date, b.due_date, b.return_date, b.status,
                   u.id as user_id, u.username, u.full_name,
                   bk.id as book_id, bk.title, bk.author
            FROM borrows b
            JOIN users u ON b.user_id = u.id
            JOIN books bk ON b.book_id = bk.id
            ORDER BY b.borrow_date DESC
        ''')).fetchall()
        
        # Chuyển đổi dữ liệu
        borrows = []
        for row in borrows_data:
            borrow = {
                'id': row.id,
                'borrow_date': row.borrow_date,
                'due_date': row.due_date,
                'return_date': row.return_date,
                'status': row.status
            }
            user = {
                'id': row.user_id,
                'username': row.username,
                'full_name': row.full_name
            }
            book = {
                'id': row.book_id,
                'title': row.title,
                'author': row.author
            }
            borrows.append((borrow, user, book))
            
    except Exception as e:
        print(f"Error querying borrows: {e}")
        traceback.print_exc()
        borrows = []
        flash('Có lỗi khi tải danh sách mượn sách', 'danger')
    
    return render_template('admin/borrows.html', borrows=borrows)

@app.route('/admin/add_book', methods=['GET', 'POST'])
@admin_required
def add_book():
    categories = Category.query.all()
    
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        category_id = request.form.get('category_id', type=int)
        description = request.form['description']
        publication_year = request.form.get('publication_year', type=int)
        language = request.form.get('language')
        pages = request.form.get('pages', type=int)
        
        # Xử lý file cover
        cover_image = None
        if 'cover' in request.files:
            file = request.files['cover']
            if file and file.filename:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'covers', filename))
                cover_image = filename
        
        # Xử lý file sách
        file_path = None
        if 'book_file' in request.files:
            file = request.files['book_file']
            if file and file.filename:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'books', filename))
                file_path = filename
        
        # Tạo sách mới (không tạo QR code ngay vì cần ID của sách)
        book = Book(
            title=title,
            author=author,
            category_id=category_id,
            description=description,
            publication_year=publication_year,
            language=language,
            pages=pages,
            cover_image=cover_image,
            file_path=file_path,
            is_available=True,
            added_by=session['user_id'],
            added_at=datetime.utcnow()  # Đảm bảo added_at là đối tượng datetime
        )
        
        # Thử lại tối đa 3 lần khi database bị lock
        max_attempts = 3
        retry_delay = 1  # giây
        
        for attempt in range(max_attempts):
            try:
                db.session.add(book)
                db.session.commit()
                
                # Tạo mã QR cho sách sau khi đã có ID
                try:
                    host_url = request.host_url.rstrip('/')
                    book.qr_code = generate_book_qr(book.id, host_url)
                    db.session.commit()
                except Exception as e:
                    print(f"Error generating QR code: {e}")
                    # Tiếp tục ngay cả khi không tạo được QR
                
                flash('Sách đã được thêm thành công!', 'success')
                return redirect(url_for('book_detail', book_id=book.id))
            except Exception as e:
                db.session.rollback()
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                    print(f"Retrying database operation, attempt {attempt + 2}")
                    continue
                else:
                    flash(f'Có lỗi xảy ra khi thêm sách: {str(e)}', 'danger')
                    print(f"Error adding book: {str(e)}")
                    break
    
    return render_template('admin/add_book.html', categories=categories)

@app.route('/admin/edit_book/<int:book_id>', methods=['GET', 'POST'])
@admin_required
def edit_book(book_id):
    book = Book.query.get_or_404(book_id)
    categories = Category.query.all()
    
    if request.method == 'POST':
        book.title = request.form['title']
        book.author = request.form['author']
        book.category_id = request.form.get('category_id', type=int)
        book.description = request.form['description']
        book.publication_year = request.form.get('publication_year', type=int)
        book.language = request.form.get('language')
        book.pages = request.form.get('pages', type=int)
        
        # Xử lý file cover mới nếu có
        if 'cover' in request.files:
            file = request.files['cover']
            if file and file.filename:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'covers', filename))
                book.cover_image = filename
        
        # Xử lý file sách mới nếu có
        if 'book_file' in request.files:
            file = request.files['book_file']
            if file and file.filename:
                filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], 'books', filename))
                book.file_path = filename
        
        # Thử lại tối đa 3 lần khi database bị lock
        max_attempts = 3
        retry_delay = 1  # giây
        
        for attempt in range(max_attempts):
            try:
                db.session.commit()
                flash('Sách đã được cập nhật thành công!', 'success')
                return redirect(url_for('book_detail', book_id=book.id))
            except Exception as e:
                db.session.rollback()
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                    print(f"Retrying database operation, attempt {attempt + 2}")
                    continue
                else:
                    flash(f'Có lỗi xảy ra khi cập nhật sách: {str(e)}', 'danger')
                    print(f"Error updating book: {str(e)}")
                    break
    
    return render_template('admin/edit_book.html', book=book, categories=categories)

@app.route('/admin/delete_book/<int:book_id>', methods=['POST'])
@admin_required
def delete_book(book_id):
    book = Book.query.get_or_404(book_id)
    
    # Xóa file cover và file sách nếu có
    if book.cover_image:
        cover_path = os.path.join(app.config['UPLOAD_FOLDER'], 'covers', book.cover_image)
        if os.path.exists(cover_path):
            os.remove(cover_path)
    
    if book.file_path:
        book_path = os.path.join(app.config['UPLOAD_FOLDER'], 'books', book.file_path)
        if os.path.exists(book_path):
            os.remove(book_path)
    
    # Xóa file QR nếu có
    if book.qr_code:
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], 'qrcodes', book.qr_code)
        if os.path.exists(qr_path):
            os.remove(qr_path)
    
    # Thử lại tối đa 3 lần khi database bị lock
    max_attempts = 3
    retry_delay = 1  # giây
    
    for attempt in range(max_attempts):
        try:
            db.session.delete(book)
            db.session.commit()
            flash('Sách đã được xóa thành công!', 'success')
            return redirect(url_for('admin_books'))
        except Exception as e:
            db.session.rollback()
            if attempt < max_attempts - 1:
                time.sleep(retry_delay)
                print(f"Retrying database operation, attempt {attempt + 2}")
                continue
            else:
                flash(f'Có lỗi xảy ra khi xóa sách: {str(e)}', 'danger')
                print(f"Error deleting book: {str(e)}")
                return redirect(url_for('admin_books'))

@app.route('/admin/add_category', methods=['GET', 'POST'])
@admin_required
def add_category():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        
        category = Category(name=name, description=description)
        
        # Thử lại tối đa 3 lần khi database bị lock
        max_attempts = 3
        retry_delay = 1  # giây
        
        for attempt in range(max_attempts):
            try:
                db.session.add(category)
                db.session.commit()
                flash('Danh mục đã được thêm thành công!', 'success')
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                db.session.rollback()
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                    print(f"Retrying database operation, attempt {attempt + 2}")
                    continue
                else:
                    flash(f'Có lỗi xảy ra khi thêm danh mục: {str(e)}', 'danger')
                    print(f"Error adding category: {str(e)}")
                    break
    
    return render_template('admin/add_category.html')

@app.route('/admin/update_borrow/<int:borrow_id>', methods=['POST'])
@admin_required
def update_borrow(borrow_id):
    try:
        status = request.form.get('status')
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        if status == 'returned':
            # Sử dụng SQL trực tiếp để cập nhật
            db.session.execute(db.text("""
                UPDATE borrows 
                SET status = 'returned', return_date = :return_date 
                WHERE id = :borrow_id
            """), {"return_date": current_time, "borrow_id": borrow_id})
        elif status == 'overdue':
            db.session.execute(db.text("""
                UPDATE borrows 
                SET status = 'overdue' 
                WHERE id = :borrow_id
            """), {"borrow_id": borrow_id})
        elif status == 'borrowed':
            db.session.execute(db.text("""
                UPDATE borrows 
                SET status = 'borrowed' 
                WHERE id = :borrow_id
            """), {"borrow_id": borrow_id})
        
        db.session.commit()
        flash('Trạng thái phiếu mượn đã được cập nhật!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating borrow: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra khi cập nhật phiếu mượn: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

# Route xuất biên lai
@app.route('/books/receipt/<int:borrow_id>')
@login_required
def borrow_receipt(borrow_id):
    # Lấy thông tin phiếu mượn
    borrow = Borrow.query.get_or_404(borrow_id)
    
    # Kiểm tra quyền truy cập
    if borrow.user_id != session['user_id'] and User.query.get(session['user_id']).role != 'admin':
        flash('Bạn không có quyền xem biên lai này!', 'danger')
        return redirect(url_for('index'))
    
    # Lấy thông tin sách
    book = Book.query.get(borrow.book_id)
    
    # Lấy thông tin người dùng
    user = User.query.get(borrow.user_id)
    
    # Xử lý ngày tháng
    borrow.borrow_date = ensure_datetime(borrow.borrow_date)
    borrow.due_date = ensure_datetime(borrow.due_date)
    
    # Tạo mã biên lai độc nhất
    try:
        if borrow.borrow_date:
            receipt_code = f"TL-{borrow.id}-{int(datetime.timestamp(borrow.borrow_date))}"
        else:
            receipt_code = f"TL-{borrow.id}-{int(datetime.utcnow().timestamp())}"
    except Exception as e:
        print(f"Error generating receipt code: {e}")
        receipt_code = f"TL-{borrow.id}-{int(datetime.utcnow().timestamp())}"
    
    # Hiển thị biên lai
    return render_template('book/receipt.html', borrow=borrow, book=book, user=user, receipt_code=receipt_code, datetime=datetime)

# Thêm route mới cho việc mượn sách
@app.route('/books/borrow/<int:book_id>', methods=['GET', 'POST'])
@login_required
def borrow_book(book_id):
    try:
        book = Book.query.get_or_404(book_id)
    except Exception as e:
        print(f"Error querying book for borrowing: {e}")
        flash('Có lỗi khi tải thông tin sách', 'danger')
        return redirect(url_for('book_list'))
    
    # Kiểm tra xem người dùng đã mượn sách này chưa và chưa trả
    try:
        existing_borrow = Borrow.query.filter_by(
            user_id=session['user_id'], 
            book_id=book_id,
            status='borrowed'
        ).first()
    except Exception as e:
        print(f"Error checking existing borrows: {e}")
        existing_borrow = None
    
    if existing_borrow:
        flash('Bạn đã mượn sách này rồi và chưa trả.', 'info')
        return redirect(url_for('book_detail', book_id=book_id))
    
    if request.method == 'POST':
        # Xác nhận mượn sách
        try:
            borrow_period = int(request.form.get('borrow_period', 14))
            # Đảm bảo borrow_period luôn là một số nguyên dương
            borrow_period = max(1, borrow_period)
        except:
            borrow_period = 14  # Mặc định 14 ngày nếu có lỗi chuyển đổi
        
        # Tạo thời gian hiện tại và hạn trả rõ ràng
        now = datetime.utcnow()
        due_date = now + timedelta(days=borrow_period)
        
        # Tạo bản ghi mượn sách
        borrow = Borrow(
            user_id=session['user_id'],
            book_id=book_id,
            borrow_date=now,
            due_date=due_date,
            status='borrowed'
        )
        
        # Thử lại tối đa 3 lần khi database bị lock
        max_attempts = 3
        retry_delay = 1  # giây
        
        for attempt in range(max_attempts):
            try:
                db.session.add(borrow)
                db.session.commit()
                flash('Bạn đã mượn sách thành công!', 'success')
                
                # Nếu người dùng chọn tải xuống ngay
                if 'download' in request.form:
                    return redirect(url_for('download_book_file', book_id=book_id))
                
                # Chuyển đến trang biên lai
                return redirect(url_for('borrow_receipt', borrow_id=borrow.id))
            except Exception as e:
                db.session.rollback()
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
                    print(f"Retrying database operation, attempt {attempt + 2}")
                    continue
                else:
                    flash(f'Có lỗi xảy ra khi mượn sách: {str(e)}', 'danger')
                    print(f"Error borrowing book: {str(e)}")
                    return redirect(url_for('book_detail', book_id=book_id))
    
    # Hiển thị form xác nhận mượn sách
    return render_template('book/borrow.html', book=book)

# Sửa đổi route download_book để chỉ kiểm tra đã mượn chưa
@app.route('/books/download/<int:book_id>')
@login_required
def download_book(book_id):
    book = Book.query.get_or_404(book_id)
    
    # Kiểm tra xem người dùng đã mượn sách này chưa
    borrow = Borrow.query.filter_by(
        user_id=session['user_id'], 
        book_id=book_id,
        status='borrowed'
    ).first()
    
    if not borrow:
        flash('Bạn cần mượn sách trước khi tải xuống.', 'warning')
        return redirect(url_for('borrow_book', book_id=book_id))
    
    # Chuyển hướng đến tải file
    return redirect(url_for('download_book_file', book_id=book_id))

# Thêm route mới chỉ để tải file sách
@app.route('/books/download_file/<int:book_id>')
@login_required
def download_book_file(book_id):
    book = Book.query.get_or_404(book_id)
    
    # Kiểm tra file tồn tại
    if not book.file_path:
        flash('File sách không tồn tại.', 'danger')
        return redirect(url_for('book_detail', book_id=book_id))
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'books', book.file_path)
    if not os.path.exists(file_path):
        flash('File sách không tồn tại.', 'danger')
        return redirect(url_for('book_detail', book_id=book_id))
    
    # Trả về file để tải xuống
    return redirect(url_for('static', filename=f'uploads/books/{book.file_path}'))

# Thêm alias route để hỗ trợ cả hai tên
@app.route('/books/book_download/<int:book_id>')
@login_required
def book_download(book_id):
    # Chuyển hướng đến route download_book
    return redirect(url_for('download_book', book_id=book_id))

@app.route('/admin/mark_returned/<int:borrow_id>')
@admin_required
def mark_returned(borrow_id):
    try:
        # Sử dụng SQL trực tiếp để cập nhật
        current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        db.session.execute(db.text("""
            UPDATE borrows 
            SET status = 'returned', return_date = :return_date 
            WHERE id = :borrow_id
        """), {"return_date": current_time, "borrow_id": borrow_id})
        
        db.session.commit()
        flash('Phiếu mượn đã được đánh dấu là đã trả!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error marking borrow as returned: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

@app.route('/admin/mark_overdue/<int:borrow_id>')
@admin_required
def mark_overdue(borrow_id):
    try:
        # Sử dụng SQL trực tiếp để cập nhật
        db.session.execute(db.text("""
            UPDATE borrows 
            SET status = 'overdue'
            WHERE id = :borrow_id
        """), {"borrow_id": borrow_id})
        
        db.session.commit()
        flash('Phiếu mượn đã được đánh dấu là quá hạn!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error marking borrow as overdue: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

@app.route('/admin/fix-borrow/<int:borrow_id>')
@admin_required
def fix_borrow(borrow_id):
    try:
        # Lấy thông tin phiếu mượn
        borrow_data = db.session.execute(db.text("""
            SELECT borrow_date FROM borrows WHERE id = :borrow_id
        """), {"borrow_id": borrow_id}).fetchone()
        
        if borrow_data and borrow_data[0]:
            try:
                # Cố gắng chuyển đổi ngày tháng
                if isinstance(borrow_data[0], str):
                    borrow_date = datetime.strptime(borrow_data[0], "%Y-%m-%d %H:%M:%S")
                else:
                    borrow_date = borrow_data[0]
                
                # Tính ngày đến hạn mới và định dạng lại
                due_date = (borrow_date + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
                
                # Cập nhật hạn trả
                db.session.execute(db.text("""
                    UPDATE borrows SET due_date = :due_date WHERE id = :borrow_id
                """), {"due_date": due_date, "borrow_id": borrow_id})
                
                db.session.commit()
                flash(f'Đã sửa hạn trả cho phiếu mượn ID {borrow_id}', 'success')
            except Exception as e:
                # Nếu không thể chuyển đổi, sử dụng ngày hiện tại + 14 ngày
                due_date = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
                
                db.session.execute(db.text("""
                    UPDATE borrows SET due_date = :due_date WHERE id = :borrow_id
                """), {"due_date": due_date, "borrow_id": borrow_id})
                
                db.session.commit()
                flash(f'Đã đặt hạn trả mới cho phiếu mượn ID {borrow_id}', 'success')
        else:
            # Nếu không có borrow_date, sử dụng ngày hiện tại
            due_date = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
            
            db.session.execute(db.text("""
                UPDATE borrows SET due_date = :due_date WHERE id = :borrow_id
            """), {"due_date": due_date, "borrow_id": borrow_id})
            
            db.session.commit()
            flash(f'Đã đặt hạn trả mới cho phiếu mượn ID {borrow_id}', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error fixing borrow: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra khi sửa phiếu mượn: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

@app.route('/admin/fix-all-borrows')
@admin_required
def fix_all_borrows():
    try:
        # Tìm tất cả bản ghi mượn sách có hạn trả là null hoặc 0
        broken_borrows_data = db.session.execute(db.text("""
            SELECT id, borrow_date 
            FROM borrows 
            WHERE due_date IS NULL OR due_date = 0 OR due_date = '0'
        """)).fetchall()
        
        fixed_count = 0
        for row in broken_borrows_data:
            borrow_id = row.id
            borrow_date = row.borrow_date
            
            # Tính ngày đến hạn mới (14 ngày sau ngày mượn) và định dạng lại
            due_date = datetime.utcnow() + timedelta(days=14)
            due_date_str = due_date.strftime("%Y-%m-%d %H:%M:%S")
            
            # Cập nhật hạn trả
            db.session.execute(db.text("""
                UPDATE borrows SET due_date = :due_date WHERE id = :borrow_id
            """), {"due_date": due_date_str, "borrow_id": borrow_id})
            
            fixed_count += 1
        
        db.session.commit()
        flash(f'Đã sửa {fixed_count} phiếu mượn có hạn trả không hợp lệ', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error fixing all borrows: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra khi sửa phiếu mượn: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

@app.route('/admin/check-overdue')
@admin_required
def check_overdue():
    try:
        # Lấy ngày hiện tại
        current_date = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Tìm các phiếu mượn đã quá hạn nhưng chưa được đánh dấu
        db.session.execute(db.text("""
            UPDATE borrows 
            SET status = 'overdue' 
            WHERE status = 'borrowed' 
            AND due_date < :current_date 
            AND (return_date IS NULL OR return_date = '')
        """), {"current_date": current_date})
        
        db.session.commit()
        flash('Đã kiểm tra và cập nhật các phiếu mượn quá hạn!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error checking overdue: {e}")
        traceback.print_exc()
        flash(f'Có lỗi xảy ra khi kiểm tra quá hạn: {str(e)}', 'danger')
    
    return redirect(url_for('admin_borrows'))

# Tạo và cập nhật database
with app.app_context():
    # Tạo các bảng nếu chưa tồn tại
    db.create_all()
    
    # Kiểm tra và cập nhật cấu trúc bảng books
    try:
        # Kiểm tra xem cột cover_image có tồn tại không
        db.session.execute(db.text('SELECT cover_image FROM books LIMIT 1'))
        print("Database structure is correct!")
    except Exception as e:
        print(f"Updating database structure: {e}")
        try:
            # Thêm cột cover_image nếu chưa có
            db.session.execute(db.text('ALTER TABLE books ADD COLUMN cover_image TEXT'))
            db.session.commit()
            print("Added cover_image column to books table!")
        except Exception as alter_error:
            print(f"Error updating database: {alter_error}")
    
    # Kiểm tra và thêm cột qr_code vào bảng books nếu chưa có
    try:
        # Kiểm tra xem cột qr_code có tồn tại chưa
        db.session.execute(db.text('SELECT qr_code FROM books LIMIT 1'))
        print("QR code column already exists in books table!")
    except Exception as e:
        print(f"Adding qr_code column to books table: {e}")
        try:
            # Thêm cột qr_code nếu chưa có
            db.session.execute(db.text('ALTER TABLE books ADD COLUMN qr_code TEXT'))
            db.session.commit()
            print("Added qr_code column to books table!")
            
            # Tạo mã QR cho tất cả sách hiện có
            books = Book.query.all()
            host_url = "http://127.0.0.1:5000"  # Mặc định cho local
            
            for book in books:
                if not book.qr_code:
                    try:
                        book.qr_code = generate_book_qr(book.id, host_url)
                    except Exception as qr_err:
                        print(f"Error generating QR for book {book.id}: {qr_err}")
            
            db.session.commit()
            print(f"Generated QR codes for {len(books)} existing books!")
        except Exception as alter_error:
            print(f"Error updating database: {alter_error}")
            db.session.rollback()
    
    # Kiểm tra và cập nhật dữ liệu ngày tháng trong database
    try:
        print("Kiểm tra và cập nhật dữ liệu ngày tháng trong database...")
        
        # Cập nhật dữ liệu added_at trong bảng books
        books = Book.query.all()
        updated_books = 0
        
        for book in books:
            try:
                # Nếu added_at không phải là đối tượng datetime, cập nhật lại
                if not isinstance(book.added_at, datetime):
                    book.added_at = datetime.utcnow()
                    updated_books += 1
            except Exception as e:
                print(f"Error processing book {book.id}: {e}")
                book.added_at = datetime.utcnow()
                updated_books += 1
        
        if updated_books > 0:
            db.session.commit()
            print(f"Đã cập nhật trường added_at cho {updated_books} sách")
        
        # Cập nhật dữ liệu ngày tháng trong bảng borrows
        borrows = Borrow.query.all()
        updated_borrows = 0
        
        for borrow in borrows:
            try:
                # Cập nhật các trường ngày tháng nếu cần
                if hasattr(borrow, 'borrow_date') and not isinstance(borrow.borrow_date, datetime):
                    borrow.borrow_date = datetime.utcnow()
                    updated_borrows += 1
                
                if hasattr(borrow, 'due_date') and borrow.due_date is not None and not isinstance(borrow.due_date, datetime):
                    borrow.due_date = datetime.utcnow() + timedelta(days=14)
                    updated_borrows += 1
                
                if hasattr(borrow, 'return_date') and borrow.return_date is not None and not isinstance(borrow.return_date, datetime):
                    borrow.return_date = datetime.utcnow()
                    updated_borrows += 1
            except Exception as e:
                print(f"Error processing borrow {borrow.id}: {e}")
                # Đặt giá trị mặc định cho các trường ngày tháng
                borrow.borrow_date = datetime.utcnow()
                borrow.due_date = datetime.utcnow() + timedelta(days=14)
                if borrow.status == 'returned':
                    borrow.return_date = datetime.utcnow()
                updated_borrows += 1
        
        if updated_borrows > 0:
            db.session.commit()
            print(f"Đã cập nhật dữ liệu ngày tháng cho {updated_borrows} phiếu mượn")
        
    except Exception as e:
        print(f"Lỗi khi cập nhật dữ liệu ngày tháng: {e}")
        db.session.rollback()
    
    # Kiểm tra xem đã có admin chưa
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            password='admin',
            email='admin@thuvienso.com',
            full_name='Quản trị viên',
            role='admin',
            created_at=datetime.utcnow()  # Đảm bảo created_at là datetime
        )
        db.session.add(admin_user)
        db.session.commit()
        print("Admin account created!")
    else:
        print("Admin account already exists")
    
    # Kiểm tra có category nào chưa
    if Category.query.count() == 0:
        default_categories = [
            Category(name='Lập trình', description='Sách về lập trình và phát triển phần mềm'),
            Category(name='AI & Machine Learning', description='Sách về trí tuệ nhân tạo và học máy'),
            Category(name='Kinh doanh & Kỹ năng', description='Sách về kinh doanh và phát triển kỹ năng mềm')
        ]
        db.session.add_all(default_categories)
        db.session.commit()
        print("Default categories created!")
    
    # Tạo bảng báo cáo hàng tháng nếu chưa tồn tại
    try:
        db.session.execute(db.text('''
        CREATE TABLE IF NOT EXISTS monthly_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            report_data TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''))
        db.session.commit()
        print("Monthly reports table created/verified!")
    except Exception as e:
        print(f"Error creating monthly_reports table: {e}")

# Cấu hình logging khi không ở chế độ debug
if not app.debug:
    file_handler = RotatingFileHandler('app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Ứng dụng thư viện khởi động')

if __name__ == '__main__':
    app.run(debug=True)