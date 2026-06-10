from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import os
import io
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_padrao_seeduc")

# Conexão direta e blindada via API Web (Porta 443 HTTPS)
SUPABASE_URL = "https://igzgvommpgscswqguhvo.supabase.co"
SUPABASE_KEY = "sb_publishable_0rv-2XmhWuSOxZwgp7TcIw_6mbb-IDy"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    return True

@app.route('/init-banco-docente')
def forcar_banco():
    try:
        supabase.table("professores").select("id").limit(1).execute()
        return "Banco de dados sincronizado com sucesso na nuvem!"
    except Exception as e:
        return f"Erro real retornado pelo Supabase: {str(e)}", 500

@app.route('/')
def home():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        res = supabase.table("escolas").select("*").eq("professor_id", session['user_id']).order("nome").execute()
        escolas = res.data if res.data else []
    except Exception as e:
        print(f"Erro na home: {e}")
        escolas = []
    return render_template('index.html', escolas=escolas)

def gerar_dados_escola(escola_id):
    try:
        res_escola = supabase.table("escolas").select("*").eq("id", escola_id).single().execute()
        escola = res_escola.data
        if not escola: return None, None, None, None
    except Exception as e:
        print(f"Erro ao buscar escola: {e}")
        return None, None, None, None
        
    try:
        res_diario = supabase.table("diario_bordo").select("data, conteudo").eq("escola_id", escola_id).execute()
        datas_chamadas = res_diario.data if res_diario.data else []
    except Exception as e:
        datas_chamadas = []
        
    listagem_datas = list(set([d['data'] for d in datas_chamadas if 'data' in d]))
    listagem_datas.sort()
    conteudos_datas = {d['data']: d['conteudo'] for d in datas_chamadas if 'data' in d}

    try:
        res_alunos = supabase.table("alunos").select("*").eq("escola_id", escola_id).order("nome").execute()
        alunos_db = res_alunos.data if res_alunos.data else []
        
        res_notas = supabase.table("notas").select("*").eq("escola_id", escola_id).eq("bimestre", 1).execute()
        notas_db = {n['matricula']: n for n in res_notas.data if 'matricula' in n}
    except Exception as e:
        alunos_db, notas_db = [], {}

    try:
        res_presencas = supabase.table("diario_bordo").select("matricula, data, status_presenca").eq("escola_id", escola_id).execute()
        presencas_db = res_presencas.data if res_presencas.data else []
    except Exception as e:
        presencas_db = []
        
    mapa_presencas = {}
    for p in presencas_db:
        if 'matricula' in p and 'data' in p:
            mapa_presencas[(p['matricula'], p['data'])] = p['status_presenca']

    alunos_com_planilha = []
    for alu in alunos_db:
        historico_aluno = []
        total_faltas = 0
        for data in listagem_datas:
            status = mapa_presencas.get((alu['matricula'], data), '-')
            if status == 'F': total_faltas += 1
            historico_aluno.append({'data': data, 'status': status})
            
        n = notas_db.get(alu['matricula'], {})
        teste = float(n.get('teste') if n.get('teste') is not None else 0.0)
        prova = float(n.get('prova') if n.get('prova') is not None else 0.0)
        qualitativo = float(n.get('qualitativo') if n.get('qualitativo') is not None else 0.0)
        media = (teste + prova + qualitativo) / 3
        
        alunos_com_planilha.append({
            'matricula': alu['matricula'], 'nome': alu['nome'], 'turma': alu['turma'],
            'teste': teste, 'prova': prova, 'qualitativo': qualitativo,
            'media': round(media, 2), 'total_faltas': total_faltas, 'historico': historico_aluno
        })
        
    return escola, alunos_com_planilha, listagem_datas, conteudos_datas

@app.route('/escola/<int:escola_id>')
def school_detail(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola, alunos_com_planilha, listagem_datas, conteudos_datas = gerar_dados_escola(escola_id)
    if not escola:
        return "Unidade Escolar nao localizada.", 404

    data_actual = datetime.now().strftime('%Y-%m-%d')
    return render_template('escola.html', escola=escola, alunos=alunos_com_planilha, 
                           datas=listagem_datas, conteudos=conteudos_datas, data_hoje=data_actual)

@app.route('/exportar_excel/<int:escola_id>')
def exportar_excel(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola, alunos, datas, _ = gerar_dados_escola(escola_id)
    if not escola: return "Erro ao exportar dados.", 404
    
    linhas_planilha = []
    for alu in alunos:
        dados_aluno = {
            'Matricula': alu['matricula'],
            'Nome do Aluno': alu['nome'],
            'Turma': alu['turma'],
            'Teste': alu['teste'],
            'Prova': alu['prova'],
            'Qualitativo': alu['qualitativo'],
            'Media Final': alu['media'],
            'Total Faltas': alu['total_faltas']
        }
        for hist in alu['historico']:
            dados_aluno[f"Aula {hist['data']}"] = hist['status']
            
        linhas_planilha.append(dados_aluno)
        
    df = pd.DataFrame(linhas_planilha)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Diario de Classe')
    output.seek(0)
    
    nome_arquivo = f"Diario_Classe_CIEP_{escola_id}.xlsx"
    return send_file(output, as_attachment=True, download_name=nome_arquivo,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/fazer_chamada/<int:escola_id>', methods=['POST'])
def fazer_chamada(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    data_aula = request.form['data_aula']
    conteudo = request.form['conteudo']
    faltosos = request.form.getlist('falta_aluno')
    data_formatada = datetime.strptime(data_aula, '%Y-%m-%d').strftime('%d/%m')
    
    try:
        res_alunos = supabase.table("alunos").select("matricula").eq("escola_id", escola_id).execute()
        alunos = res_alunos.data if res_alunos.data else []
        for alu in alunos:
            mat = alu['matricula']
            status = 'F' if str(mat) in faltosos else 'P'
            supabase.table("diario_bordo").insert({
                "matricula": mat, "data": data_formatada, "status_presenca": status, 
                "conteudo": conteudo, "bimestre": 1, "escola_id": escola_id
            }).execute()
        flash("Diário de classe updated!")
    except Exception as e:
        flash(f"Erro ao atualizar chamada: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/lancar_notas_bimestre/<int:escola_id>', methods=['POST'])
def lancar_notas_bimestre(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    mat = int(request.form['matricula'])
    teste = float(request.form['teste'])
    prova = float(request.form['prova'])
    qual = float(request.form['qualitativo'])
    
    try:
        supabase.table("notas").upsert({
            "matricula": mat, "bimestre": 1, "escola_id": escola_id, 
            "teste": teste, "prova": prova, "qualitativo": qual
        }, on_conflict="matricula,bimestre").execute()
        flash("Avaliacoes lancadas.")
    except Exception as e:
        flash(f"Erro ao lancar notas: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/importar/<int:escola_id>', methods=['POST'])
def importar(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    file = request.files['file']
    if file.filename == '': return redirect(url_for('school_detail', escola_id=escola_id))
    try:
        df_topo = pd.read_csv(file, sep=',', nrows=1, header=None, encoding='utf-8')
        nome_turma = str(df_topo.iloc[0, 4]).strip()
        file.seek(0)
        df = pd.read_csv(file, sep=',', engine='python', encoding='utf-8', skiprows=2)
        df = df.dropna(subset=['ALUNO', 'NOME_COMPL'])
        
        for _, row in df.iterrows():
            matricula = int(row['ALUNO'])
            nome = str(row['NOME_COMPL']).strip()
            supabase.table("alunos").upsert({
                "matricula": matricula, "nome": nome, "turma": nome_turma, "escola_id": escola_id
            }).execute()
        flash(f"Turma {nome_turma} importada com sucesso!")
    except Exception as e: 
        flash(f"Falha na leitura do arquivo: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            res = supabase.table("professores").select("*").eq("email", request.form['email']).execute()
            users = res.data if res.data else []
            user = users[0] if users else None
            if user and check_password_hash(user['senha'], request.form['senha']):
                session['user_id'] = user['id']
                session['user_name'] = user['nome']
                return redirect(url_for('home'))
        except Exception as e:
            print(f"Erro no login: {e}")
        flash('Credenciais incorretas.')
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        hash_senha = generate_password_hash(request.form['senha'])
        try:
            supabase.table("professores").insert({
                "nome": request.form['nome'], "email": request.form['email'], "senha": hash_senha
            }).execute()
            flash('Inscricao confirmada. Faca autenticacao.')
            return redirect(url_for('login'))
        except Exception as e: 
            print(f"Erro no cadastro: {e}")
            flash('E-mail funcional ja cadastrado.')
    return render_template('cadastro.html')

@app.route('/add_escola', methods=['POST'])
def add_escola():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        supabase.table("escolas").insert({"nome": request.form['nome'], "professor_id": session['user_id']}).execute()
        flash('Nova unidade de ensino vinculada.')
    except Exception as e:
        print(f"Erro ao adicionar escola: {e}")
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
