from flask import Flask, render_template, request, redirect, url_for, session, flash
import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_padrao_seeduc")

# Troque a frase abaixo pelo seu link real do Supabase (mantenha as aspas!)
DATABASE_URL = "postgresql://postgres.igzgvommpgscswqguhvo:Li548423312$@aws-0-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
if DATABASE_URL and "sslmode=" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)

def init_db():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS professores (id SERIAL PRIMARY KEY, nome TEXT, email TEXT UNIQUE, senha TEXT)')
        cursor.execute('CREATE TABLE IF NOT EXISTS escolas (id SERIAL PRIMARY KEY, nome TEXT, professor_id INTEGER REFERENCES professores(id))')
        cursor.execute('CREATE TABLE IF NOT EXISTS alunos (matricula BIGINT PRIMARY KEY, nome TEXT, turma TEXT, escola_id INTEGER REFERENCES escolas(id))')
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diario_bordo (
                id SERIAL PRIMARY KEY, matricula BIGINT, data TEXT, status_presenca TEXT, conteudo TEXT, bimestre INTEGER, escola_id INTEGER REFERENCES escolas(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notas (
                id SERIAL PRIMARY KEY, matricula BIGINT, bimestre INTEGER, escola_id INTEGER REFERENCES escolas(id),
                teste REAL DEFAULT 0.0, prova REAL DEFAULT 0.0, qualitativo REAL DEFAULT 0.0,
                UNIQUE(matricula, bimestre)
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao inicializar banco: {e}")
        return False

@app.route('/init-banco-docente')
def forcar_banco():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        # Se conectou, tenta criar as tabelas
        sucesso = init_db()
        return "Banco de dados sincronizado com sucesso na nuvem!" if sucesso else "Conectou, mas falhou ao criar tabelas."
    except Exception as e:
        # Se falhar, joga o erro real na tela do navegador
        return f"Erro real retornado pelo Supabase: {str(e)}", 500
def forcar_banco():
    sucesso = init_db()
    return "Banco de dados sincronizado com sucesso na nuvem!" if sucesso else "Falha ao conectar no Supabase."

@app.route('/')
def home():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM escolas WHERE professor_id = %s ORDER BY nome', (session['user_id'],))
    escolas = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', escolas=escolas)

@app.route('/escola/<int:escola_id>')
def school_detail(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM escolas WHERE id = %s AND professor_id = %s', (escola_id, session['user_id']))
    escola = cursor.fetchone()
    if escola is None:
        cursor.close()
        conn.close()
        return "Unidade Escolar não localizada ou Acesso Negado.", 403
        
    cursor.execute("SELECT DISTINCT data, conteudo FROM diario_bordo WHERE escola_id = %s ORDER BY data ASC", (escola_id,))
    datas_chamadas = cursor.fetchall()
    listagem_datas = [d['data'] for d in datas_chamadas]
    conteudos_datas = {d['data']: d['conteudo'] for d in datas_chamadas}

    query = """
        SELECT a.matricula, a.nome, a.turma,
               COALESCE(n.teste, 0.0) as teste, COALESCE(n.prova, 0.0) as prova, COALESCE(n.qualitativo, 0.0) as qualitativo,
               ((COALESCE(n.teste, 0.0) + COALESCE(n.prova, 0.0) + COALESCE(n.qualitativo, 0.0)) / 3) as media
        FROM alunos a
        LEFT JOIN notas n ON a.matricula = n.matricula AND n.escola_id = %s AND n.bimestre = 1
        WHERE a.escola_id = %s ORDER BY a.nome
    """
    cursor.execute(query, (escola_id, escola_id))
    alunos_db = cursor.fetchall()

    cursor.execute("SELECT matricula, data, status_presenca FROM diario_bordo WHERE escola_id = %s", (escola_id,))
    presencas_db = cursor.fetchall()
    
    mapa_presencas = {}
    for p in presencas_db:
        mapa_presencas[(p['matricula'], p['data'])] = p['status_presenca']

    alunos_com_planilha = []
    for alu in alunos_db:
        historico_aluno = []
        total_faltas = 0
        for data in listagem_datas:
            status = mapa_presencas.get((alu['matricula'], data), '-')
            if status == 'F': total_faltas += 1
            historico_aluno.append({'data': data, 'status': status})
            
        alunos_com_planilha.append({
            'matricula': alu['matricula'], 'nome': alu['nome'], 'turma': alu['turma'],
            'teste': alu['teste'], 'prova': alu['prova'], 'qualitativo': alu['qualitativo'],
            'media': alu['media'], 'total_faltas': total_faltas, 'historico': historico_aluno
        })

    cursor.close()
    conn.close()
    data_actual = datetime.now().strftime('%Y-%m-%d')
    return render_template('escola.html', escola=escola, alunos=alunos_com_planilha, 
                           datas=listagem_datas, conteudos=conteudos_datas, data_hoje=data_actual)

@app.route('/fazer_chamada/<int:escola_id>', methods=['POST'])
def fazer_chamada(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    data_aula = request.form['data_aula']
    conteudo = request.form['conteudo']
    faltosos = request.form.getlist('falta_aluno')
    data_formatada = datetime.strptime(data_aula, '%Y-%m-%d').strftime('%d/%m')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT matricula FROM alunos WHERE escola_id = %s", (escola_id,))
    alunos = cursor.fetchall()
    
    for alu in alunos:
        mat = alu['matricula']
        status = 'F' if str(mat) in faltosos else 'P'
        cursor.execute("""
            INSERT INTO diario_bordo (matricula, data, status_presenca, conteudo, bimestre, escola_id)
            VALUES (%s, %s, %s, %s, 1, %s)
        """, (mat, data_formatada, status, conteudo, escola_id))
        
    conn.commit()
    cursor.close()
    conn.close()
    flash("Diário de classe atualizado!")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/lancar_notas_bimestre/<int:escola_id>', methods=['POST'])
def lancar_notas_bimestre(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    mat = int(request.form['matricula'])
    teste = float(request.form['teste'])
    prova = float(request.form['prova'])
    qual = float(request.form['qualitativo'])
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notas (matricula, bimestre, escola_id, teste, prova, qualitativo) VALUES (%s, 1, %s, %s, %s, %s)
        ON CONFLICT(matricula, bimestre) DO UPDATE SET teste=EXCLUDED.teste, prova=EXCLUDED.prova, qualitativo=EXCLUDED.qualitativo
    """, (mat, escola_id, teste, prova, qual))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Avaliações lançadas.")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/importar/<int:escola_id>', methods=['POST'])
def importar(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    file = request.files['file']
    if file.filename == '': return redirect(url_for('school_detail', escola_id=escola_id))
    try:
        df_topo = pd.read_csv(file, sep=',', nrows=1, header=None, encoding='utf-8')
        nome_turma = str(df_topo.iloc[0, 4]).strip()
        file.seek(0)
        df = pd.read_csv(file, sep=',', engine='python', encoding='utf-8', skiprows=2)
        df = df.dropna(subset=['ALUNO', 'NOME_COMPL'])
        conn = get_db()
        cursor = conn.cursor()
        for _, row in df.iterrows():
            matricula = int(row['ALUNO'])
            nome = str(row['NOME_COMPL']).strip()
            cursor.execute("""
                INSERT INTO alunos (matricula, nome, turma, escola_id) VALUES (%s, %s, %s, %s)
                ON CONFLICT (matricula) DO UPDATE SET nome=EXCLUDED.nome, turma=EXCLUDED.turma, escola_id=EXCLUDED.escola_id
            """, (matricula, nome, nome_turma, escola_id))
        conn.commit()
        cursor.close()
        conn.close()
        flash(f"Turma {nome_turma} importada com sucesso!")
    except Exception as e: flash(f"Falha na leitura do arquivo: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM professores WHERE email = %s', (request.form['email'],))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and check_password_hash(user['senha'], request.form['senha']):
            session['user_id'] = user['id']
            session['user_name'] = user['nome']
            return redirect(url_for('home'))
        flash('Credenciais incorretas.')
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        conn = get_db()
        cursor = conn.cursor()
        hash_senha = generate_password_hash(request.form['senha'])
        try:
            cursor.execute('INSERT INTO professores (nome, email, senha) VALUES (%s, %s, %s)', (request.form['nome'], request.form['email'], hash_senha))
            conn.commit()
            flash('Inscrição confirmada. Faça autenticação.')
            return redirect(url_for('login'))
        except: flash('E-mail funcional já cadastrado.')
        finally: 
            cursor.close()
            conn.close()
    return render_template('cadastro.html')

@app.route('/add_escola', methods=['POST'])
def add_escola():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO escolas (nome, professor_id) VALUES (%s, %s)', (request.form['nome'], session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Nova unidade de ensino vinculada.')
    return redirect(url_for('home'))

@app.route('/manifest.json')
def manifest():
    return {
        "name": "Diário Docente Inteligente",
        "short_name": "Diário Docente",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#1e3d59",
        "theme_color": "#1e3d59",
        "orientation": "portrait",
        "icons": [{"src": "https://cdn-icons-png.flaticon.com/512/3470/3470088.png", "sizes": "512x512", "type": "image/png"}]
    }, 200, {'Content-Type': 'application/json'}

@app.route('/service-worker.js')
def service_worker():
    return "self.addEventListener('install', e => {}); self.addEventListener('fetch', e => {});", 200, {'Content-Type': 'application/javascript'}

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
