# analytics.py
from flask import Blueprint, render_template, jsonify, request, current_app
from models import Book, User, Borrow, Category
from extensions import db
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
import json
import calendar

analytics = Blueprint('analytics', __name__)

@analytics.route('/admin/analytics')
def analytics_dashboard():
    return render_template('admin/analytics.html')

@analytics.route('/api/analytics/summary')
def get_summary():
    # Thống kê tổng quan
    total_books = Book.query.count()
    total_users = User.query.filter_by(role='user').count()
    total_borrows = Borrow.query.count()
    
    try:
        active_borrows = Borrow.query.filter_by(status='borrowed').count()
    except Exception as e:
        print(f"Error counting active_borrows: {e}")
        active_borrows = 0
    
    # Tính toán sách quá hạn
    today = datetime.utcnow()
    try:
        overdue_count = Borrow.query.filter(
            Borrow.status == 'borrowed',
            Borrow.due_date < today
        ).count()
    except Exception as e:
        print(f"Error counting overdue_count: {e}")
        overdue_count = 0
    
    # Người dùng mới trong 30 ngày qua
    thirty_days_ago = today - timedelta(days=30)
    try:
        new_users_count = User.query.filter(
            User.created_at >= thirty_days_ago
        ).count()
    except Exception as e:
        print(f"Error counting new_users: {e}")
        new_users_count = 0
    
    return jsonify({
        'total_books': total_books,
        'total_users': total_users,
        'total_borrows': total_borrows,
        'active_borrows': active_borrows,
        'overdue_count': overdue_count,
        'new_users_count': new_users_count
    })

@analytics.route('/api/analytics/top-borrowers')
def get_top_borrowers():
    # Khoảng thời gian (mặc định 30 ngày)
    days = request.args.get('days', 30, type=int)
    limit = request.args.get('limit', 5, type=int)
    
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Truy vấn top người mượn
        result = db.session.query(
            User.id, User.username, User.full_name, func.count(Borrow.id).label('borrow_count')
        ).join(
            Borrow, User.id == Borrow.user_id
        ).filter(
            Borrow.borrow_date >= start_date
        ).group_by(
            User.id
        ).order_by(
            desc('borrow_count')
        ).limit(limit).all()
        
        top_borrowers = [
            {
                'user_id': row[0],
                'username': row[1],
                'full_name': row[2],
                'borrow_count': row[3]
            } for row in result
        ]
    except Exception as e:
        print(f"Error getting top borrowers: {e}")
        top_borrowers = []
    
    return jsonify(top_borrowers)

@analytics.route('/api/analytics/top-books')
def get_top_books():
    # Khoảng thời gian (mặc định 30 ngày)
    days = request.args.get('days', 30, type=int)
    limit = request.args.get('limit', 5, type=int)
    
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Truy vấn top sách
        result = db.session.query(
            Book.id, Book.title, Book.author, func.count(Borrow.id).label('borrow_count')
        ).join(
            Borrow, Book.id == Borrow.book_id
        ).filter(
            Borrow.borrow_date >= start_date
        ).group_by(
            Book.id
        ).order_by(
            desc('borrow_count')
        ).limit(limit).all()
        
        top_books = [
            {
                'book_id': row[0],
                'title': row[1],
                'author': row[2],
                'borrow_count': row[3]
            } for row in result
        ]
    except Exception as e:
        print(f"Error getting top books: {e}")
        top_books = []
    
    return jsonify(top_books)

@analytics.route('/api/analytics/monthly-stats')
def get_monthly_stats():
    # Số tháng cần lấy dữ liệu (mặc định 12 tháng)
    months = request.args.get('months', 12, type=int)
    
    try:
        # Lấy thời gian bắt đầu
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30 * months)
        
        # Truy vấn số lượng mượn theo tháng
        borrow_results = db.session.query(
            func.strftime('%Y-%m', Borrow.borrow_date).label('month'),
            func.count().label('count')
        ).filter(
            Borrow.borrow_date.between(start_date, end_date)
        ).group_by(
            'month'
        ).all()
        
        borrow_data = {row[0]: row[1] for row in borrow_results}
        
        # Truy vấn số lượng trả theo tháng
        return_results = db.session.query(
            func.strftime('%Y-%m', Borrow.return_date).label('month'),
            func.count().label('count')
        ).filter(
            Borrow.return_date.between(start_date, end_date)
        ).group_by(
            'month'
        ).all()
        
        return_data = {row[0]: row[1] for row in return_results}
        
        # Truy vấn số người dùng mới theo tháng
        new_user_results = db.session.query(
            func.strftime('%Y-%m', User.created_at).label('month'),
            func.count().label('count')
        ).filter(
            User.created_at.between(start_date, end_date)
        ).group_by(
            'month'
        ).all()
        
        new_user_data = {row[0]: row[1] for row in new_user_results}
        
        # Tạo danh sách tháng
        months_list = []
        current_date = start_date
        while current_date <= end_date:
            month_key = current_date.strftime('%Y-%m')
            months_list.append(month_key)
            # Tăng 1 tháng
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)
        
        # Tạo dữ liệu đầy đủ
        chart_data = []
        for month in months_list:
            month_data = {
                'month': month,
                'borrows': borrow_data.get(month, 0),
                'returns': return_data.get(month, 0),
                'new_users': new_user_data.get(month, 0)
            }
            chart_data.append(month_data)
    except Exception as e:
        print(f"Error getting monthly stats: {e}")
        chart_data = []
    
    return jsonify(chart_data)

@analytics.route('/api/analytics/category-stats')
def get_category_stats():
    try:
        # Truy vấn số lượng mượn theo danh mục
        result = db.session.query(
            Category.name, func.count(Borrow.id).label('borrow_count')
        ).join(
            Book, Book.category_id == Category.id
        ).join(
            Borrow, Borrow.book_id == Book.id
        ).group_by(
            Category.id
        ).order_by(
            desc('borrow_count')
        ).all()
        
        category_stats = [
            {
                'category': row[0],
                'count': row[1]
            } for row in result
        ]
    except Exception as e:
        print(f"Error getting category stats: {e}")
        category_stats = []
    
    return jsonify(category_stats)

@analytics.route('/api/analytics/overdue-books')
def get_overdue_books():
    try:
        today = datetime.utcnow()
        
        # Truy vấn sách quá hạn
        result = db.session.query(
            User.username, User.full_name, Book.title, Book.author,
            Borrow.borrow_date, Borrow.due_date
        ).join(
            User, User.id == Borrow.user_id
        ).join(
            Book, Book.id == Borrow.book_id
        ).filter(
            Borrow.status == 'borrowed',
            Borrow.due_date < today
        ).order_by(
            Borrow.due_date
        ).all()
        
        overdue_books = []
        for row in result:
            try:
                if isinstance(row[5], datetime):
                    days_overdue = (today - row[5]).days
                else:
                    # Nếu due_date không phải datetime, xử lý tùy trường hợp
                    days_overdue = "N/A"
                
                overdue_books.append({
                    'username': row[0],
                    'full_name': row[1],
                    'book_title': row[2],
                    'book_author': row[3],
                    'borrow_date': row[4].strftime('%d/%m/%Y') if isinstance(row[4], datetime) else str(row[4]),
                    'due_date': row[5].strftime('%d/%m/%Y') if isinstance(row[5], datetime) else str(row[5]),
                    'days_overdue': days_overdue
                })
            except Exception as e:
                print(f"Error processing overdue book: {e}")
                continue
    except Exception as e:
        print(f"Error getting overdue books: {e}")
        overdue_books = []
    
    return jsonify(overdue_books)

@analytics.route('/api/analytics/generate-report')
def generate_monthly_report():
    try:
        # Lấy thông tin tháng trước
        today = datetime.utcnow()
        first_day_current_month = today.replace(day=1)
        last_day_previous_month = first_day_current_month - timedelta(days=1)
        first_day_previous_month = last_day_previous_month.replace(day=1)
        
        # Định dạng các ngày
        start_date = first_day_previous_month
        end_date = last_day_previous_month
        
        # Lấy tổng số lượt mượn trong tháng
        borrow_count = Borrow.query.filter(
            Borrow.borrow_date.between(start_date, end_date)
        ).count()
        
        # Lấy tổng số lượt trả trong tháng
        return_count = Borrow.query.filter(
            Borrow.return_date.between(start_date, end_date)
        ).count()
        
        # Lấy người mượn nhiều nhất
        top_borrower_result = db.session.query(
            User.username, User.full_name, func.count(Borrow.id).label('borrow_count')
        ).join(
            Borrow, User.id == Borrow.user_id
        ).filter(
            Borrow.borrow_date.between(start_date, end_date)
        ).group_by(
            User.id
        ).order_by(
            desc('borrow_count')
        ).first()
        
        top_borrower = {
            'username': top_borrower_result[0] if top_borrower_result else None,
            'full_name': top_borrower_result[1] if top_borrower_result else None,
            'borrow_count': top_borrower_result[2] if top_borrower_result else 0
        }
        
        # Lấy sách được mượn nhiều nhất
        top_book_result = db.session.query(
            Book.title, Book.author, func.count(Borrow.id).label('borrow_count')
        ).join(
            Borrow, Book.id == Borrow.book_id
        ).filter(
            Borrow.borrow_date.between(start_date, end_date)
        ).group_by(
            Book.id
        ).order_by(
            desc('borrow_count')
        ).first()
        
        top_book = {
            'title': top_book_result[0] if top_book_result else None,
            'author': top_book_result[1] if top_book_result else None,
            'borrow_count': top_book_result[2] if top_book_result else 0
        }
        
        # Tạo báo cáo
        report = {
            'month': last_day_previous_month.strftime('%m/%Y'),
            'month_name': calendar.month_name[last_day_previous_month.month],
            'year': last_day_previous_month.year,
            'borrow_count': borrow_count,
            'return_count': return_count,
            'top_borrower': top_borrower,
            'top_book': top_book,
            'generated_at': today.strftime('%d/%m/%Y %H:%M:%S')
        }
        
        # Lưu báo cáo vào database
        try:
            db.session.execute(db.text('''
                INSERT INTO monthly_reports (month, year, report_data, generated_at)
                VALUES (:month, :year, :report_data, :generated_at)
            '''), {
                'month': last_day_previous_month.month,
                'year': last_day_previous_month.year,
                'report_data': json.dumps(report),
                'generated_at': today.strftime('%Y-%m-%d %H:%M:%S')
            })
            db.session.commit()
        except Exception as e:
            print(f"Error saving report to database: {e}")
            db.session.rollback()
    except Exception as e:
        print(f"Error generating monthly report: {e}")
        report = {
            'month': 'N/A',
            'month_name': 'N/A',
            'year': datetime.utcnow().year,
            'borrow_count': 0,
            'return_count': 0,
            'top_borrower': {'username': None, 'full_name': None, 'borrow_count': 0},
            'top_book': {'title': None, 'author': None, 'borrow_count': 0},
            'generated_at': datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S'),
            'error': str(e)
        }
    
    return jsonify(report)