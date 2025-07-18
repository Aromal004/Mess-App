from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# Change this to match your Postgres credentials
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:2004@localhost:5432/canteen_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define database model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    student_id = db.Column(db.String(20), nullable=False)
    item = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Create the tables
with app.app_context():
    db.create_all()

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
def admin():
    orders = Order.query.order_by(Order.timestamp.desc()).all()
    return render_template('admin.html', orders=orders, total=len(orders))

if __name__ == '__main__':
    app.run(debug=True)
