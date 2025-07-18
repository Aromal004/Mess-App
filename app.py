from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a strong secret in production

# PostgreSQL config
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:2004@localhost:5432/canteen_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------- Models ----------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'admin' or 'student'

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    item = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_coupon = db.Column(db.Boolean, default=False)
    priority = db.Column(db.Boolean, default=False)
    paid = db.Column(db.Boolean, default=False)

class Streak(db.Model):
    __tablename__ = 'streaks'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    last_order_date = db.Column(db.Date)
    streak_count = db.Column(db.Integer, default=0)

# ---------- Constants ----------

ITEM_PRICES = {
    'meal': 50,
    'chai': 10,
    'snack': 20
}

SERVING_TIME = datetime.now().replace(hour=20, minute=0, second=0, microsecond=0)
CANCEL_CUTOFF = SERVING_TIME.replace(hour=19, minute=0)

# ---------- Helpers ----------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ---------- Routes ----------

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            return redirect('/admin' if user.role == 'admin' else '/order')
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('signup.html')
        hashed_pw = generate_password_hash(password)
        user = User(username=username, password=hashed_pw, role='student')
        db.session.add(user)
        db.session.commit()
        flash('Account created. Please log in.')
        return redirect('/login')
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/order', methods=['GET', 'POST'])
@login_required
def order():
    if session.get('role') != 'student':
        return redirect('/login')

    now = datetime.now()
    cancel_cutoff = now.replace(hour=19, minute=0, second=0, microsecond=0)
    student_id = session['user_id']
    today = datetime.today().date()

    if request.method == 'POST':
        if 'delete' in request.form:
            if now <= cancel_cutoff:
                Order.query.filter(
                    db.func.date(Order.timestamp) == today,
                    Order.student_id == student_id
                ).delete()
                db.session.commit()
                flash("Your order was deleted.")
            else:
                flash("⛔ You cannot delete orders after 7:00 PM.")
            return redirect('/order')

        items = request.form.getlist('item')
        if not items:
            flash("Please select at least one item.")
            return redirect('/order')

        session['pending_items'] = items  # Save selection for payment
        return redirect('/pay')

    existing = Order.query.filter(
        db.func.date(Order.timestamp) == today,
        Order.student_id == student_id
    ).all()

    return render_template('order.html', existing=existing, before_cutoff=(now <= cancel_cutoff))



@app.route('/pay', methods=['GET', 'POST'])
@login_required
def pay():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session['user_id']
    today = datetime.today().date()
    items = session.get('pending_items', [])

    if not items:
        flash("No items selected for payment.")
        return redirect('/order')

    total = sum(ITEM_PRICES.get(item.lower(), 0) for item in items)

    if request.method == 'POST':
        # --- Streak Logic ---
        streak = Streak.query.filter_by(student_id=student_id).first()
        if streak:
            if streak.last_order_date == today - timedelta(days=1):
                streak.streak_count += 1
            else:
                streak.streak_count = 1
            streak.last_order_date = today
        else:
            streak = Streak(student_id=student_id, last_order_date=today, streak_count=1)
            db.session.add(streak)

        use_coupon = False
        is_priority = False
        if streak.streak_count == 3:
            use_coupon = True
            is_priority = True
            streak.streak_count = 0

        # Delete existing orders for today before placing new ones
        Order.query.filter(
            db.func.date(Order.timestamp) == today,
            Order.student_id == student_id
        ).delete()

        # Create new orders
        for item in items:
            is_free = use_coupon and ITEM_PRICES.get(item.lower(), 0) > 0
            order = Order(
                student_id=student_id,
                item=item,
                is_coupon=is_free,
                priority=is_priority,
                paid=True
            )
            db.session.add(order)

        db.session.commit()
        session.pop('pending_items', None)
        return render_template('payment_success.html', total=total)

    return render_template('payment.html', items=items, total=total, ITEM_PRICES=ITEM_PRICES)



@app.route('/admin')
@login_required
def admin():
    if session.get('role') != 'admin':
        return redirect('/login')

    today = datetime.today().date()
    sort_by = request.args.get('sort', 'priority')  # default

    if sort_by == 'time':
        orders = Order.query.filter(
            db.func.date(Order.timestamp) == today
        ).order_by(Order.timestamp).all()
    else:
        orders = Order.query.filter(
            db.func.date(Order.timestamp) == today
        ).order_by(Order.priority.desc(), Order.timestamp).all()

    item_counts = db.session.query(Order.item, db.func.count(Order.item)).filter(
        db.func.date(Order.timestamp) == today
    ).group_by(Order.item).all()

    total_orders = sum(count for _, count in item_counts)

    return render_template('admin.html',
        orders=orders,
        total=total_orders,
        item_counts=item_counts,
        current_sort=sort_by
    )

# ---------- DB Init ----------

with app.app_context():
    db.create_all()

# ---------- Run Server ----------

if __name__ == '__main__':
    app.run(debug=True)
