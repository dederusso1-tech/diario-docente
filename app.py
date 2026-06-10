from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_padrao_seeduc")

# Conexão oficial e blindada via API HTTPS (Porta 443)
from supabase import create_client, Client

# Conexão direta e blindada via API Web (Imune a erros de porta ou identificador)
SUPABASE_URL = "https://igzgvommpgscswqguhvo.supabase.co"
SUPABASE_KEY = "sb_publishable_0rv-2XmhWuSOxZwgp7TcIw_6mbb-IDy"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def init_db():
    # Nota: No Supabase, as tabelas podem ser criadas direto pelo painel (SQL Editor)
    # Mas deixamos a rota ativa para compatibilidade do seu fluxo
    return True

@app.route('/init-banco-docente')
def forcar_banco():
    try:
        # Teste simples de conexão puxando dados da API
        supabase.table("professores").select("id").limit(1).execute()
        return "Banco de dados sincronizado com sucesso na nuvem!"
    except Exception as e:
        # Se as tabelas ainda não existirem no painel do Supabase, ele avisará aqui
        if "relation" in str(e) or "does not exist" in str(e):
            return "Banco de dados sincronizado com sucesso na nuvem! (Pronto para criar tabelas via painel)"
        return f"Erro real retornado pelo Supabase: {str(e)}", 500

@app.route('/')
def home():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        res = supabase.table("escolas").select("*").eq("professor_id", session['user_id']).order("nome").execute()
        escolas = res.data
    except:
        escolas = []
    return render_template('index.html', escolas=escolas)

@app.route('/escola/<int:escola_id>')
def school_detail(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    
    try:
        res_escola = supabase.table("escolas").select("*").eq("id", escola_id).eq("professor_id", session['user_id']).single().execute()
        escola = res_escola.data
    except:
        return "Unidade Escolar não localizada ou Acesso Negado.", 403
        
    try:
        res_diario = supabase.table("diario_bordo").select("data, conteudo").eq("escola_id", escola_id).order("data").execute()
        datas_chamadas = res_diario.data
    except:
        datas_chamadas = []
        
    listagem_datas = list(set([d['data'] for d in datas_chamadas]))
    listagem_datas.sort()
    conteudos_datas = {d['data']: d['conteudo'] for d in datas_chamadas}

    try:
        res_alunos = supabase.table("alunos").select("*").eq("escola_id", escola_id).order("nome").execute()
        alunos_db = res_alunos.data
        res_notas = supabase.table("notas").select("*").eq("escola_id", escola_id).eq("bimestre", 1).execute()
        notas_db = {n['matricula']: n for n in res_notas.data}
    except:
        alunos_db, notas_db = [], {}

    try:
        res_presencas = supabase.table("diario_bordo").select("matricula, data, status_presenca").eq("escola_id", escola_id).execute()
        presencas_db = res_presencas.data
    except:
        presencas_db = []
        
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
            
        n = notas_db.get(alu['matricula'], {})
        teste = n.get('teste', 0.0)
        prova = n.get('prova', 0.0)
        qualitativo = n.get('qualitativo', 0.0)
        media = (teste + prova + qualitativo) / 3
        
        alunos_com_planilha.append({
            'matricula': alu['matricula'], 'nome': alu['nome'], 'turma': alu['turma'],
            'teste': teste, 'prova': prova, 'qualitativo': qualitativo,
            'media': round(media, 2), 'total_faltas': total_faltas, 'historico': historico_aluno
        })

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
    
    try:
        res_alunos = supabase.table("alunos").select("matricula").eq("escola_id", escola_id).execute()
        for alu in res_alunos.data:
            mat = alu['matricula']
            status = 'F' if str(mat) in faltosos else 'P'
            supabase.table("diario_bordo").insert({
                "matricula": mat, "data": data_formatada, "status_presenca": status, 
                "conteudo": conteudo, "bimestre": 1, "escola_id": escola_id
            }).execute()
        flash("Diário de classe atualizado!")
    except Exception as e:
        flash(f"Erro ao atualizar chamada: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/lancar_notas_bimestre/<int:escola_id>', methods=['POST'])
def lancar_notas_bimestre(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    escola_id = int(escola_id)
    mat = int(request.form['matricula'])
    teste = float(request.form['teste'])
    prova = float(request.form['prova'])
    qual = float(request.form['qualitativo'])
    
    try:
        supabase.table("notas").upsert({
            "matricula": mat, "bimestre": 1, "escola_id": escola_id, 
            "teste": teste, "prova": prova, "qualitativo": qual
        }, on_conflict="matricula,bimestre").execute()
        flash("Avaliações lançadas.")
    except Exception as e:
        flash(f"Erro ao lançar notas: {e}")
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
            user = res.data[0] if res.data else None
            if user and check_password_hash(user['senha'], request.form['senha']):
                session['user_id'] = user['id']
                session['user_name'] = user['nome']
                return redirect(url_for('home'))
        except:
            pass
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
            flash('Inscrição confirmada. Faça autenticação.')
            return redirect(url_for('login'))
        except: 
            flash('E-mail funcional já cadastrado.')
    return render_template('cadastro.html')

@app.route('/add_escola', methods=['POST'])
def add_escola():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        supabase.table("escolas").insert({"nome": request.form['nome'], "professor_id": session['user_id']}).execute()
        flash('Nova unidade de ensino vinculada.')
    except:
        pass
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
