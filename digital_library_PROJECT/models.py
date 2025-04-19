from extensions import db
from datetime import datetime
from flask_login import UserMixin

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'user' hoặc 'admin'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Thiết lập quan hệ với bảng borrows
    borrows = db.relationship('Borrow', backref='user', lazy=True)

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    
    # Thiết lập quan hệ với bảng books - đây là phần quan trọng cần sửa
    books = db.relationship('Book', backref='category_info', lazy=True)

class Book(db.Model):
    __tablename__ = 'books'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    description = db.Column(db.Text)
    publication_year = db.Column(db.Integer)
    language = db.Column(db.String(50))
    pages = db.Column(db.Integer)
    is_available = db.Column(db.Boolean, default=True)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    cover_image = db.Column(db.String(255))
    file_path = db.Column(db.String(255))
    qr_code = db.Column(db.String(255))
    
    # Thiết lập quan hệ với bảng borrows
    borrows = db.relationship('Borrow', backref='book', lazy=True)
    
    # Không thiết lập relationship ở đây vì đã được thiết lập trong model Category

class Borrow(db.Model):
    __tablename__ = 'borrows'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False)
    borrow_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='borrowed')  # borrowed, returned, overdue
    
    def __init__(self, user_id, book_id, borrow_date=None, due_date=None, status='borrowed'):
        self.user_id = user_id
        self.book_id = book_id
        if borrow_date:
            self.borrow_date = borrow_date
        if due_date:
            self.due_date = due_date
        self.status = status
    
    def __repr__(self):
        return f'<Borrow {self.id}: User {self.user_id}, Book {self.book_id}>'