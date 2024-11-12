from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate  # Flask-Migrateをインポート
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from dotenv import load_dotenv

import openai
import os

load_dotenv()

# OpenAI APIキーの設定（セキュリティ上、環境変数から取得することを推奨）
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'

# ファイルアップロードの設定
UPLOAD_FOLDER = os.path.join('static', 'images', 'icons')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ディレクトリが存在しない場合は作成
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
socketio = SocketIO(app)

# ユーザーモデルの定義
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    icon = db.Column(db.String(150), nullable=True)  # アイコン画像のパスを保存

# カテゴリーモデルの定義
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    threads = db.relationship('Thread', backref='category', lazy=True)

# スレッドモデルの定義
class Thread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    messages = db.relationship('Message', backref='thread', lazy=True)

# メッセージモデルの定義
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_name = db.Column(db.String(150), nullable=False)
    user_icon = db.Column(db.String(150), nullable=True)  # ユーザーのアイコンパスを保存
    thread_id = db.Column(db.Integer, db.ForeignKey('thread.id'), nullable=False)

# データベースを初期化
with app.app_context():
    db.create_all()

# ログインが必要なルートを保護するデコレータ
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# アップロードされたファイルが許可された拡張子か確認する関数
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ホームページ：カテゴリーの一覧を表示
@app.route('/')
@login_required
def index():
    categories = Category.query.all()
    return render_template('index.html', categories=categories)

# カテゴリー管理ページ
@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    if request.method == 'POST':
        name = request.form['name']
        new_category = Category(name=name)
        db.session.add(new_category)
        db.session.commit()
        return redirect(url_for('index'))
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

# 特定カテゴリーのスレッド一覧ページ
@app.route('/category/<int:category_id>/threads', methods=['GET', 'POST'])
@login_required
def threads(category_id):
    category = Category.query.get_or_404(category_id)
    if request.method == 'POST':
        title = request.form['title']
        new_thread = Thread(title=title, category=category)
        db.session.add(new_thread)
        db.session.commit()
        return redirect(url_for('threads', category_id=category.id))
    threads = Thread.query.filter_by(category_id=category_id).all()
    return render_template('threads.html', category=category, threads=threads)

# 特定スレッドのメッセージページ
@app.route('/thread/<int:thread_id>', methods=['GET'])
@login_required
def thread(thread_id):
    thread = Thread.query.get_or_404(thread_id)
    messages = Message.query.filter_by(thread_id=thread_id).order_by(Message.timestamp.asc()).all()
    return render_template('thread.html', thread=thread, messages=messages)

# 新規ユーザー登録
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        # アイコン画像の処理
        icon = None
        if 'icon' in request.files:
            file = request.files['icon']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # ユニークなファイル名を生成
                unique_filename = f"{name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                icon = f'/static/images/icons/{unique_filename}'
        
        if User.query.filter_by(name=name).first():
            return 'ユーザー名は既に使用されています'
        password_hash = generate_password_hash(password)
        new_user = User(name=name, password_hash=password_hash, icon=icon)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

# ユーザーログイン
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        user = User.query.filter_by(name=name).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['name'] = user.name
            session['icon'] = user.icon  # アイコンパスをセッションに保存
            return redirect(url_for('index'))
        else:
            return 'ログイン情報が間違っています'
    return render_template('login.html')

# ユーザーログアウト
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('name', None)
    session.pop('icon', None)
    return redirect(url_for('login'))

# クライアントから送信されたメッセージを処理
@socketio.on('send_message')
def handle_message(data):
    if 'user_id' in session:
        message_text = data['message']
        timestamp = datetime.now()
        name = session['name']
        icon = session.get('icon')  # セッションからアイコンパスを取得
        thread_id = data['thread_id']
        new_message = Message(message=message_text, timestamp=timestamp, user_name=name, user_icon=icon, thread_id=thread_id)
        db.session.add(new_message)
        db.session.commit()
        msg_data = {
            'message': message_text,
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'name': name,
            'icon': icon
        }
        join_room(f'thread_{thread_id}')
        emit('new_message', msg_data, room=f'thread_{thread_id}')
    else:
        emit('new_message', {'message': 'ログインしてください', 'timestamp': '', 'name': '', 'icon': None})

@app.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot():
    return render_template('chatbot.html')

@socketio.on('send_bot_message')
def handle_bot_message(data):
    if 'user_id' in session:
        message_text = data['message']
        timestamp = datetime.now()
        
        # OpenAI APIを呼び出して、ChatGPTの応答を取得
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": message_text}]
        )
        bot_reply = response['choices'][0]['message']['content']
        
        # チャットボットの応答をクライアントに送信
        emit('bot_response', {
            'message': bot_reply,
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'name': 'ChatGPT',
            'icon': '/static/images/bot_icon.png'  # デフォルトのボットアイコンを指定
        })
    else:
        emit('bot_response', {'message': 'ログインしてください', 'timestamp': '', 'name': '', 'icon': None})

if __name__ == '__main__':
    socketio.run(app, debug=True)
