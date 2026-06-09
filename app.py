from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import pandas as pd
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "chave_criptografica_segura_seeduc_rj"
DB_NAME = "plataforma_docente.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS professores (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, email TEXT UNIQUE, senha TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS escolas (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, professor_id INTEGER, FOREIGN KEY(professor_id) REFERENCES professores(id))')
    cursor.execute('CREATE TABLE IF NOT EXISTS alunos (matricula INTEGER PRIMARY KEY, nome TEXT, turma TEXT, escola_id INTEGER, FOREIGN KEY(escola_id) REFERENCES escolas(id))')
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS diario_bordo (
            id INTEGER PRIMARY KEY AUTOINCREMENT, matricula INTEGER, data TEXT, status_presenca TEXT, conteudo TEXT, bimestre INTEGER, escola_id INTEGER,
            FOREIGN KEY(matricula) REFERENCES alunos(matricula), FOREIGN KEY(escola_id) REFERENCES escolas(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, matricula INTEGER, bimestre INTEGER, escola_id INTEGER,
            teste REAL DEFAULT 0.0, prova REAL DEFAULT 0.0, qualitativo REAL DEFAULT 0.0,
            FOREIGN KEY(matricula) REFERENCES alunos(matricula), FOREIGN KEY(escola_id) REFERENCES escolas(id),
            UNIQUE(matricula, bimestre)
        )
    """)
    conn.commit()
    conn.close()

@app.route('/')
def home():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    escolas = conn.execute('SELECT * FROM escolas WHERE professor_id = ? ORDER BY nome', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('index.html', escolas=escolas)

@app.route('/escola/<int:escola_id>')
def escola_detalhe(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    escola = conn.execute('SELECT * FROM escolas WHERE id = ? AND professor_id = ?', (escola_id, session['user_id'])).fetchone()
    if escola is None:
        conn.close()
        return "Unidade Escolar não localizada ou Acesso Negado.", 403
        
    # 1. Busca datas únicas de chamadas - Versão Corrigida em Linha Única sem quebra de aspas
    datas_chamadas = conn.execute("SELECT DISTINCT data, conteudo FROM diario_bordo WHERE escola_id = ? ORDER BY data ASC", (escola_id,)).fetchall()
    
    listagem_datas = [d['data'] for d in datas_chamadas]
    conteudos_datas = {d['data']: d['conteudo'] for d in datas_chamadas}

    # 2. Busca todos os alunos da escola
    alunos_db = conn.execute("""
        SELECT a.matricula, a.nome, a.turma,
               COALESCE(n.teste, 0.0) as teste, COALESCE(n.prova, 0.0) as prova, COALESCE(n.qualitativo, 0.0) as qualitativo,
               ((COALESCE(n.teste, 0.0) + COALESCE(n.prova, 0.0) + COALESCE(n.qualitativo, 0.0)) / 3) as media
        FROM alunos a
        LEFT JOIN notas n ON a.matricula = n.matricula AND n.escola_id = ? AND n.bimestre = 1
        WHERE a.escola_id = ?
        ORDER BY a.turma, a.nome
    """, (escola_id, escola_id)).fetchall()

    # 3. Busca todo o histórico de presenças para cruzar na planilha
    presencas_db = conn.execute("SELECT matricula, data, status_presenca FROM diario_bordo WHERE escola_id = ?", (escola_id,)).fetchall()
    
    mapa_presencas = {}
    for p in presencas_db:
        mapa_presencas[(p['matricula'], p['data'])] = p['status_presenca']

    # 4. Estrutura a lista final de alunos injetando o histórico de dias
    alunos_com_planilha = []
    for alu in alunos_db:
        historico_aluno = []
        total_faltas = 0
        for data in listagem_datas:
            status = mapa_presencas.get((alu['matricula'], data), '-')
            if status == 'F': total_faltas += 1
            historico_aluno.append({'data': data, 'status': status})
            
        alunos_com_planilha.append({
            'matricula': alu['matricula'],
            'nome': alu['nome'],
            'turma': alu['turma'],
            'teste': alu['teste'],
            'prova': alu['prova'],
            'qualitativo': alu['qualitativo'],
            'media': alu['media'],
            'total_faltas': total_faltas,
            'historico': historico_aluno
        })

    conn.close()
    data_actual = datetime.now().strftime('%Y-%m-%d')
    return render_template('escola.html', escola=escola, alunos=alunos_com_planilha, 
                           datas=listagem_datas, conteudos=conteudos_datas, data_hoje=data_actual)

@app.route('/fazer_chamada/<int:escola_id>', methods=['POST'])
def fazer_chamada(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    data_aula = request.form['data_aula']
    conteudo = request.form['conteudo']
    faltosos = request.form.getlist('falta_aluno')
    
    data_formatada = datetime.strptime(data_aula, '%Y-%m-%d').strftime('%d/%m')
    
    conn = get_db()
    cursor = conn.cursor()
    alunos = cursor.execute("SELECT matricula FROM alunos WHERE escola_id = ?", (escola_id,)).fetchall()
    
    for alu in alunos:
        mat = alu['matricula']
        status = 'F' if str(mat) in faltosos else 'P'
        
        cursor.execute("""
            INSERT INTO diario_bordo (matricula, data, status_presenca, conteudo, bimestre, escola_id)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (mat, data_formatada, status, conteudo, escola_id))
        
    conn.commit()
    conn.close()
    flash("Diário de classe atualizado com sucesso!")
    return redirect(url_for('escola_detalhe', escola_id=escola_id))

@app.route('/lancar_notas_bimestre/<int:escola_id>', methods=['POST'])
def lancar_notas_bimestre(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    mat = request.form['matricula']
    teste = request.form['teste']
    prova = request.form['prova']
    qual = request.form['qualitativo']
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notas (matricula, bimestre, escola_id, teste, prova, qualitativo) VALUES (?, 1, ?, ?, ?, ?)
        ON CONFLICT(matricula, bimestre) DO UPDATE SET teste=excluded.teste, prova=excluded.prova, qualitativo=excluded.qualitativo
    """, (int(mat), escola_id, float(teste), float(prova), float(qual)))
    conn.commit()
    conn.close()
    flash("Avaliações lançadas no diário e médias recalculadas.")
    return redirect(url_for('escola_detalhe', escola_id=escola_id))

@app.route('/importar/<int:escola_id>', methods=['POST'])
def importar(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    file = request.files['file']
    if file.filename == '': return redirect(url_for('escola_detalhe', escola_id=escola_id))
    try:
        df_topo = pd.read_csv(file, sep=',', nrows=1, header=None, encoding='utf-8')
        nome_turma = str(df_topo.iloc[0, 4]).strip()
        file.seek(0)
        df = pd.read_csv(file, sep=',', engine='python', encoding='utf-8', skiprows=2)
        df = df.dropna(subset=['ALUNO', 'NOME_COMPL'])
        conn = get_db()
        for _, row in df.iterrows():
            matricula = int(row['ALUNO'])
            nome = str(row['NOME_COMPL']).strip()
            conn.execute('INSERT OR REPLACE INTO alunos (matricula, nome, turma, escola_id) VALUES (?, ?, ?, ?)', (matricula, nome, nome_turma, escola_id))
        conn.commit()
        conn.close()
        flash(f"Carga realizada! Turma {nome_turma} importada com sucesso para a caderneta.")
    except Exception as e: flash(f"Falha na leitura do arquivo padrão SEEDUC: {e}")
    return redirect(url_for('escola_detalhe', escola_id=escola_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        user = conn.execute('SELECT * FROM professores WHERE email = ?', (request.form['email'],)).fetchone()
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
        hash_senha = generate_password_hash(request.form['senha'])
        try:
            conn.execute('INSERT INTO professores (nome, email, senha) VALUES (?, ?, ?)', (request.form['nome'], request.form['email'], hash_senha))
            conn.commit()
            flash('Inscrição confirmada. Faça autenticação.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError: flash('E-mail funcional já cadastrado no sistema.')
        finally: conn.close()
    return render_template('cadastro.html')

@app.route('/add_escola', methods=['POST'])
def add_escola():
    if 'user_id' not in session: return redirect(url_for('login'))
    conn = get_db()
    conn.execute('INSERT INTO escolas (nome, professor_id) VALUES (?, ?)', (request.form['nome'], session['user_id']))
    conn.commit()
    conn.close()
    flash('Nova unidade de ensino vinculada.')
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=8080)