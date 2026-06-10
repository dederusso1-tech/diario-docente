from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import os
import io
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave_secreta_padrao_seeduc")

SUPABASE_URL = "https://igzgvommpgscswqguhvo.supabase.co"
SUPABASE_KEY = "sb_publishable_0rv-2XmhWuSOxZwgp7TcIw_6mbb-IDy"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def home():
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        res = supabase.table("escolas").select("*").eq("professor_id", session['user_id']).order("nome").execute()
        escolas = res.data if res.data else []
    except Exception:
        escolas = []
    return render_template('index.html', escolas=escolas)

@app.route('/escola/<int:escola_id>')
def school_detail(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        res_escola = supabase.table("escolas").select("*").eq("id", escola_id).single().execute()
        escola = res_escola.data
        
        res_alunos = supabase.table("alunos").select("*").eq("escola_id", escola_id).order("nome").execute()
        alunos_db = res_alunos.data if res_alunos.data else []
        
        res_diario = supabase.table("diario_bordo").select("data, conteudo").eq("escola_id", escola_id).execute()
        datas_db = res_diario.data if res_diario.data else []
        
        listagem_datas = list(set([d['data'] for d in datas_db if 'data' in d]))
        listagem_datas.sort()
        conteudos_datas = {d['data']: d['conteudo'] for d in datas_db if 'data' in d}
        
        res_notas = supabase.table("notas").select("*").eq("escola_id", escola_id).eq("bimestre", 1).execute()
        notas_db = {n['matricula']: n for n in res_notas.data if 'matricula' in n}
        
        res_presencas = supabase.table("diario_bordo").select("matricula, data, status_presenca").eq("escola_id", escola_id).execute()
        presencas_db = res_presencas.data if res_presencas.data else []
        mapa_p = {(p['matricula'], p['data']): p['status_presenca'] for p in presencas_db if 'matricula' in p}
        
        alunos_com_planilha = []
        for alu in alunos_db:
            historico = []
            total_faltas = 0
            for data in listagem_datas:
                status = mapa_p.get((alu['matricula'], data), '-')
                if status == 'F': total_faltas += 1
                historico.append({'data': data, 'status': status})
                
            n = notas_db.get(alu['matricula'], {})
            t = float(n.get('teste') or 0.0)
            p = float(n.get('prova') or 0.0)
            q = float(n.get('qualitativo') or 0.0)
            media = (t + p + q) / 3
            
            alunos_com_planilha.append({
                'matricula': alu['matricula'], 'nome': alu['nome'], 'turma': alu['turma'],
                'teste': t, 'prova': p, 'qualitativo': q, 'media': round(media, 2),
                'total_faltas': total_faltas, 'historico': historico
            })
            
        data_actual = datetime.now().strftime('%Y-%m-%d')
        return render_template('escola.html', escola=escola, alunos=alunos_com_planilha, 
                               datas=listagem_datas, conteudos=conteudos_datas, data_hoje=data_actual)
    except Exception as e:
        return f"Erro ao carregar caderneta: {str(e)}", 500

@app.route('/exportar_excel/<int:escola_id>')
def exportar_excel(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        res_escola = supabase.table("escolas").select("*").eq("id", escola_id).single().execute()
        escola = res_escola.data
        
        res_alunos = supabase.table("alunos").select("*").eq("escola_id", escola_id).order("nome").execute()
        alunos_db = res_alunos.data if res_alunos.data else []
        
        res_diario = supabase.table("diario_bordo").select("data").eq("escola_id", escola_id).execute()
        listagem_datas = list(set([d['data'] for d in res_diario.data if 'data' in d])) if res_diario.data else []
        listagem_datas.sort()
        
        res_notas = supabase.table("notas").select("*").eq("escola_id", escola_id).eq("bimestre", 1).execute()
        notas_db = {n['matricula']: n for n in res_notas.data}
        
        res_presencas = supabase.table("diario_bordo").select("matricula, data, status_presenca").eq("escola_id", escola_id).execute()
        mapa_p = {(p['matricula'], p['data']): p['status_presenca'] for p in res_presencas.data} if res_presencas.data else {}
        
        linhas = []
        for alu in alunos_db:
            n = notas_db.get(alu['matricula'], {})
            t = float(n.get('teste') or 0.0)
            p = float(n.get('prova') or 0.0)
            q = float(n.get('qualitativo') or 0.0)
            media = round((t + p + q) / 3, 2)
            
            total_faltas = 0
            dados_aluno = {
                'Matrícula': alu['matricula'], 'Nome do Aluno': alu['nome'], 'Turma': alu['turma'],
                'Teste': t, 'Prova': p, 'Qualitativo': q, 'Média Final': media
            }
            for d in listagem_datas:
                status = mapa_p.get((alu['matricula'], d), '-')
                if status == 'F': total_faltas += 1
                dados_aluno[f"Aula {d}"] = status
                
            dados_aluno['Total Faltas'] = total_faltas
            linhas.append(dados_aluno)
            
        df = pd.DataFrame(linhas)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Diário')
        output.seek(0)
        
        return send_file(output, as_attachment=True, download_name=f"Diario_CIEP_{escola_id}.xlsx", 
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        return f"Erro na exportação: {str(e)}", 500

@app.route('/fazer_chamada/<int:escola_id>', methods=['POST'])
def fazer_chamada(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    data_aula = request.form['data_aula']
    conteudo = request.form['conteudo']
    faltosos = request.form.getlist('falta_aluno')
    data_formatada = datetime.strptime(data_aula, '%Y-%m-%d').strftime('%d/%m')
    try:
        res_alunos = supabase.table("alunos").select("matricula").eq("escola_id", escola_id).execute()
        for alu in (res_alunos.data or []):
            mat = alu['matricula']
            status = 'F' if str(mat) in faltosos else 'P'
            supabase.table("diario_bordo").insert({
                "matricula": mat, "data": data_formatada, "status_presenca": status, 
                "conteudo": conteudo, "bimestre": 1, "escola_id": escola_id
            }).execute()
        flash("Diário de classe updated!")
    except Exception as e:
        flash(f"Erro na chamada: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/lancar_notas_bimestre/<int:escola_id>', methods=['POST'])
def lancar_notas_bimestre(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try:
        supabase.table("notas").upsert({
            "matricula": int(request.form['matricula']), "bimestre": 1, "escola_id": escola_id, 
            "teste": float(request.form['teste']), "prova": float(request.form['prova']), "qualitativo": float(request.form['qualitativo'])
        }, on_conflict="matricula,bimestre").execute()
    except Exception:
        pass
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/importar/<int:escola_id>', methods=['POST'])
def importar(escola_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    file = request.files['file']
    if file.filename != '':
        try:
            df_topo = pd.read_csv(file, sep=',', nrows=1, header=None, encoding='utf-8')
            nome_turma = str(df_topo.iloc[0, 4]).strip()
            file.seek(0)
            df = pd.read_csv(file, sep=',', engine='python', encoding='utf-8', skiprows=2).dropna(subset=['ALUNO', 'NOME_COMPL'])
            for _, row in df.iterrows():
                supabase.table("alunos").upsert({
                    "matricula": int(row['ALUNO']), "nome": str(row['NOME_COMPL']).strip(), "turma": nome_turma, "escola_id": escola_id
                }).execute()
            flash(f"Turma {nome_turma} importada!")
        except Exception as e:
            flash(f"Erro na importação: {e}")
    return redirect(url_for('school_detail', escola_id=escola_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        res = supabase.table("professores").select("*").eq("email", request.form['email']).execute()
        if res.data and check_password_hash(res.data[0]['senha'], request.form['senha']):
            session['user_id'] = res.data[0]['id']
            session['user_name'] = res.data[0]['nome']
            return redirect(url_for('home'))
        flash('Credenciais incorretas.')
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        try:
            supabase.table("professores").insert({
                "nome": request.form['nome'], "email": request.form['email'], "senha": generate_password_hash(request.form['senha'])
            }).execute()
            return redirect(url_for('login'))
        except Exception:
            flash('E-mail já cadastrado.')
    return render_template('cadastro.html')

@app.route('/add_escola', methods=['POST'])
def add_escola():
    if 'user_id' not in session: return redirect(url_for('login'))
    supabase.table("escolas").insert({"nome": request.form['nome'], "professor_id": session['user_id']}).execute()
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
