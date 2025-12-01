from flask import Flask, render_template, send_from_directory, redirect, url_for, request, session, flash
import io, sys, os, sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# Import the example functions
from exemple_btx import exemple_btx_complet, etude_parametrique_reflux

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change_this_secret_for_prod')

# Folder where generated images/html are saved
OUTPUT_DIR = os.path.dirname(__file__)

# Database for users
DB_PATH = os.path.join(OUTPUT_DIR, 'users.db')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def get_user(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, password_hash, is_admin FROM users WHERE username=?', (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {'username': row[0], 'password_hash': row[1], 'is_admin': bool(row[2])}


def add_user(username, password_hash, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)',
                  (username, password_hash, int(bool(is_admin))))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False
    conn.close()
    return True


def list_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username, is_admin FROM users')
    rows = c.fetchall()
    conn.close()
    return [{'username': r[0], 'is_admin': bool(r[1])} for r in rows]


def set_admin(username, is_admin):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET is_admin=? WHERE username=?', (int(bool(is_admin)), username))
    conn.commit()
    conn.close()


def ensure_default_admin():
    # Create default admin if no users exist
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    n = c.fetchone()[0]
    conn.close()
    if n == 0:
        # default admin/admin (please change)
        add_user('admin', generate_password_hash('admin'), is_admin=True)
        print('Created default admin user: admin / admin (change password)')

@app.route('/')
def index():
    # show current sandbox mode if stored in session
    sandbox = session.get('sandbox', 'allow-scripts')
    username = session.get('username')
    return render_template('index.html', sandbox=sandbox, username=username)


# (deprecated JSON helpers removed) use SQLite helper functions above


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if get_user(username) is not None:
            return render_template('register.html', error='Utilisateur déjà existant')
        add_user(username, generate_password_hash(password), is_admin=False)
        session['username'] = username
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        u = get_user(username)
        if u is None or not check_password_hash(u['password_hash'], password):
            return render_template('login.html', error='Identifiants invalides')
        session['username'] = username
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin():
    # accessible only to admin users
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))
    u = get_user(username)
    if not u or not u.get('is_admin'):
        return "Access denied", 403

    # files list
    files = []
    for entry in os.listdir(OUTPUT_DIR):
        if entry.lower().endswith(('.png', '.html')):
            path = os.path.join(OUTPUT_DIR, entry)
            st = os.stat(path)
            files.append({'name': entry, 'size': st.st_size, 'mtime': st.st_mtime})

    users = list_users()
    return render_template('admin.html', files=files, users=users)


@app.route('/admin/delete', methods=['POST'])
def admin_delete():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))
    u = get_user(username)
    if not u or not u.get('is_admin'):
        return "Access denied", 403
    fname = request.form.get('filename')
    if not fname:
        return redirect(url_for('admin'))
    path = os.path.join(OUTPUT_DIR, fname)
    if os.path.exists(path):
        try:
            os.remove(path)
            flash(f'Removed {fname}')
        except Exception as e:
            flash(str(e))
    return redirect(url_for('admin'))


@app.route('/admin/toggle_admin', methods=['POST'])
def admin_toggle():
    username = session.get('username')
    if not username:
        return redirect(url_for('login'))
    u = get_user(username)
    if not u or not u.get('is_admin'):
        return "Access denied", 403
    target = request.form.get('target')
    if not target:
        return redirect(url_for('admin'))
    target_user = get_user(target)
    if not target_user:
        flash('User not found')
        return redirect(url_for('admin'))
    # toggle
    new_admin = not target_user.get('is_admin')
    set_admin(target, new_admin)
    flash(f"Set admin={new_admin} for {target}")
    return redirect(url_for('admin'))


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/run')
def run():
    """Run the distillation example and capture stdout output."""
    # require login
    if 'username' not in session:
        return redirect(url_for('login'))

    # Allow sandbox mode selection stored in session or query
    sandbox_mode = request.args.get('sandbox') or session.get('sandbox', 'allow-scripts')

    # Save sandbox selection back to session
    session['sandbox'] = sandbox_mode

    # Capture stdout for both runs
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    # Prevent interactive Matplotlib windows from blocking
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt_show_backup = plt.show
        plt.show = lambda *a, **k: None
    except Exception:
        plt_show_backup = None

    try:
        # Run main example
        results, thermo, visualizer = exemple_btx_complet()
        # Run parametric reflux study to generate its outputs as well
        try:
            etude_parametrique_reflux()
        except Exception as e:
            print(f"ERROR running reflux study: {e}")
    except Exception as e:
        print(f"ERROR running simulation: {e}")
    finally:
        # restore stdout and plt.show
        sys.stdout = old_stdout
        if plt_show_backup is not None:
            try:
                import matplotlib.pyplot as plt
                plt.show = plt_show_backup
            except Exception:
                pass

    output = buf.getvalue()

    # Collect generated images and interactive html (common names)
    files = {}
    candidates = [
        'btx_bilan_matiere.png',
        'btx_shortcut_results.png',
        'btx_composition_profiles.png',
        'btx_temperature_profile.png',
        'btx_etude_reflux.png',
        'composition_profiles_interactive.html'
    ]
    for name in candidates:
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.exists(path):
            files[name] = url_for('static_file', filename=name)

    # Add timestamp
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    username = session.get('username')
    return render_template('results.html', output=output, files=files, ts=ts, sandbox_mode=sandbox_mode, username=username)

@app.route('/files/<path:filename>')
def static_file(filename):
    # Serve files from the project folder
    return send_from_directory(OUTPUT_DIR, filename)

if __name__ == '__main__':
    # Ensure DB exists and a default admin is present
    try:
        init_db()
        ensure_default_admin()
    except Exception as e:
        print('DB init error:', e)
    app.run(host='127.0.0.1', port=5000, debug=True)
