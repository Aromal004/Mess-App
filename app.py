from flask import Flask, render_template, request, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:2004@localhost:5432/canteen_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), nullable=False)
    item = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- Basic Auth Setup ---
def check_auth(username, password):
    return username == 'admin' and password == '123'

def authenticate():
    return Response(
        'Access Denied. Please provide valid credentials.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

@app.route('/logout')
def logout():
    return Response('''
        <html>
            <head>
                <title>Logged Out</title>
            </head>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h2>You have been logged out</h2>
                <p>Browser credentials were cleared.</p>
                <a href="/" style="margin-top: 20px; display: inline-block; padding: 10px 20px;
                    background: #007bff; color: white; text-decoration: none; border-radius: 5px;">
                    Go to Home
                </a>
            </body>
        </html>
    ''', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})



def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/order', methods=['POST'])
def order():
    name = request.form['name']
    student_id = request.form['student_id']
    item = request.form['item']

    today_count = Order.query.filter(db.func.date(Order.timestamp) == datetime.today().date()).count()
    if today_count >= 200:
        return "Sorry, maximum 200 meals ordered for today!"

    new_order = Order(name=name, student_id=student_id, item=item)
    db.session.add(new_order)
    db.session.commit()

    return render_template('confirm.html', name=name, item=item)

@app.route('/admin')
@requires_auth
def admin():
    orders = Order.query.order_by(Order.timestamp.desc()).all()
    return render_template('admin.html', orders=orders, total=len(orders))

if __name__ == '__main__':
    app.run(debug=True)
