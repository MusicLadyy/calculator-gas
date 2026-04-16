from flask import Flask, render_template, request, jsonify, session, send_file
import json
import math
import io
import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from utils import *

app = Flask(__name__)
app.secret_key = 'gas-calculator-secret-key'

# Регистрация русского шрифта
FONT_PATH = os.path.join(os.path.dirname(__file__), 'shrift', 'DejaVuSans.ttf')
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))
    print("Шрифт DejaVuSans успешно загружен")
else:
    print(f"Шрифт не найден по пути: {FONT_PATH}")
    print("Будет использован шрифт Helvetica по умолчанию")
    

# Загрузка справочников
with open('data.json', 'r', encoding='utf-8') as f:
    COMPONENTS_DATA = json.load(f)

COMPONENTS_LIST = list(COMPONENTS_DATA.keys())


@app.route('/')
def index():
    return render_template('base.html', components=COMPONENTS_LIST)


@app.route('/get_components_data')
def get_components_data():
    return jsonify(COMPONENTS_DATA)


@app.route('/calculate_composition', methods=['POST'])
def calculate_composition():
    data = request.json
    composition = data.get('composition', {})
    for comp in composition:
        composition[comp] = float(composition[comp])
    
    Msm = calculate_Msm(composition)
    rho_bar = calculate_relative_density(Msm)
    rho_std = calculate_rho_std(Msm)
    P_kr, T_kr, omega_cm = calculate_pseudocritical(composition)
    
    return jsonify({
        'Msm': Msm,
        'rho_bar': rho_bar,
        'rho_std': rho_std,
        'P_kr': P_kr,
        'T_kr': T_kr,
        'omega_cm': omega_cm
    })


@app.route('/calculate_critical', methods=['POST'])
def calculate_critical():
    data = request.json
    composition = data.get('composition', {})
    P = data.get('P', 15)
    T = data.get('T', 320)
    method = data.get('method', 'kay')
    
    if method == 'kay':
        P_kr, T_kr, _ = calculate_pseudocritical(composition)
    else:
        Msm = calculate_Msm(composition)
        rho_bar = calculate_relative_density(Msm)
        P_kr = 4.892 - 0.4048 * rho_bar
        T_kr = 94.717 - 170.8 * rho_bar
    
    Ppr = P / P_kr
    Tpr = T / T_kr
    
    return jsonify({
        'P_kr': round(P_kr, 4),
        'T_kr': round(T_kr, 2),
        'Ppr': round(Ppr, 4),
        'Tpr': round(Tpr, 4)
    })


@app.route('/calculate_z', methods=['POST'])
def calculate_z():
    data = request.json
    composition = data.get('composition', {})
    for comp in composition:
        composition[comp] = float(composition[comp])
    
    P = float(data.get('P', 15))
    T = float(data.get('T', 320))
    
    P_kr, T_kr, omega_cm = calculate_pseudocritical(composition)
    Ppr = P / P_kr
    Tpr = T / T_kr
    
    results = {
        'method1': calculate_Z_brown_katz(Ppr, Tpr),
        'method2': calculate_Z_gurevich(Ppr, Tpr),
        'method3': calculate_Z_two_param(composition, Ppr, Tpr),
        'method4': calculate_Z_peng_robinson(composition, Ppr, Tpr, omega_cm),
        'method5': calculate_Z_redlich_kwong(Ppr, Tpr),
        'method6': calculate_Z_three_param(composition, Ppr, Tpr, omega_cm)
    }
    
    return jsonify({
        'Ppr': round(Ppr, 4),
        'Tpr': round(Tpr, 4),
        'results': results
    })


@app.route('/calculate_properties', methods=['POST'])
def calculate_properties():
    data = request.json
    composition = data.get('composition', {})
    for comp in composition:
        composition[comp] = float(composition[comp])
    
    P = float(data.get('P', 15))
    T = float(data.get('T', 320))
    Z = float(data.get('Z', 0.874))
    
    Msm = calculate_Msm(composition)
    rho_std = calculate_rho_std(Msm)
    P_kr, T_kr, _ = calculate_pseudocritical(composition)
    Ppr = P / P_kr
    Tpr = T / T_kr
    
    density = calculate_density(P, T, rho_std, Z)
    viscosity = calculate_viscosity(Ppr, Tpr)
    cp = calculate_Cp(composition, Msm, Ppr, Tpr)
    water = calculate_water_content(P, T)
    
    return jsonify({
        'density': density,
        'viscosity': viscosity,
        'Cp': cp,
        'water_content': water
    })


@app.route('/calculate_joule', methods=['POST'])
def calculate_joule():
    data = request.json
    composition = data.get('composition', {})
    for comp in composition:
        composition[comp] = float(composition[comp])
    
    P1 = float(data.get('P1', 15))
    P2 = float(data.get('P2', 5))
    T1 = float(data.get('T1', 320))
    Z = float(data.get('Z', 0.874))
    
    Msm = calculate_Msm(composition)
    P_kr, T_kr, _ = calculate_pseudocritical(composition)
    Ppr = P1 / P_kr
    Tpr = T1 / T_kr
    
    cp = calculate_Cp(composition, Msm, Ppr, Tpr)
    Di, delta_T, T2 = calculate_joule_thomson(Ppr, Tpr, cp, P1, P2, T1)
    
    return jsonify({
        'Ppr_avg': round(Ppr, 4),
        'Di': Di,
        'delta_T': delta_T,
        'T2': T2,
        'T2_C': round(T2 - 273.15, 2)
    })


@app.route('/export_pdf', methods=['POST'])
def export_pdf():
    data = request.json
    
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Используем русский шрифт, если он загружен
    try:
        c.setFont('DejaVuSans', 16)
        font_available = True
    except:
        c.setFont('Helvetica-Bold', 16)
        font_available = False
        print("Используется шрифт Helvetica (кириллица может отображаться некорректно)")
    
    # Заголовок
    c.drawString(30, height - 40, "ОТЧЁТ О СВОЙСТВАХ ГАЗА")
    
    c.setFont('DejaVuSans' if font_available else 'Helvetica', 9)
    c.drawString(30, height - 60, f"Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}")
    
    y = height - 90
    
    def add_line(text):
        nonlocal y
        if y < 50:
            c.showPage()
            y = height - 50
            c.setFont('DejaVuSans' if font_available else 'Helvetica', 10)
        c.drawString(30, y, text)
        y -= 16
    
    c.setFont('DejaVuSans' if font_available else 'Helvetica', 10)
    
    # 1. Состав газа
    add_line("")
    add_line("СОСТАВ ГАЗА (мольные доли):")
    composition = data.get('composition', {})
    for comp, val in composition.items():
        add_line(f"  {comp} = {val*100:.2f} %")
    
    # 2. Параметры расчёта
    add_line("")
    add_line("ПАРАМЕТРЫ РАСЧЁТА:")
    add_line(f"  Давление P = {data.get('P', '—')} МПа")
    add_line(f"  Температура T = {data.get('T', '—')} К")
    add_line(f"  Молекулярная масса Mсм = {data.get('Msm', '—')} кг/кмоль")
    add_line(f"  Относительная плотность ρ̅ = {data.get('rho_bar', '—')}")
    add_line(f"  Плотность при ст.усл. ρст = {data.get('rho_std', '—')} кг/м³")
    add_line(f"  Псевдокритическое давление Pкр = {data.get('P_kr', '—')} МПа")
    add_line(f"  Псевдокритическая температура Tкр = {data.get('T_kr', '—')} К")
    add_line(f"  Приведённое давление Pпр = {data.get('Ppr', '—')}")
    add_line(f"  Приведённая температура Tпр = {data.get('Tpr', '—')}")
    
    # 3. Коэффициент сверхсжимаемости Z
    add_line("")
    add_line("КОЭФФИЦИЕНТ СВЕРХСЖИМАЕМОСТИ Z:")
    all_z = data.get('all_Z', {})
    add_line(f"  Метод 1 (Браун-Катц) = {all_z.get('method1', '—')}")
    add_line(f"  Метод 2 (Гуревич-Латонов) = {all_z.get('method2', '—')}")
    add_line(f"  Метод 3 (Двухпараметрический) = {all_z.get('method3', '—')}")
    add_line(f"  Метод 4 (Пенг-Робинсон) = {all_z.get('method4', '—')}")
    add_line(f"  Метод 5 (Редлих-Квонг) = {all_z.get('method5', '—')}")
    add_line(f"  Метод 6 (Трёхпараметрический) = {all_z.get('method6', '—')}")
    add_line(f"  → Рекомендуемое значение Z = {data.get('Z', '—')}")
    
    # 4. Физические свойства
    add_line("")
    add_line("ФИЗИЧЕСКИЕ СВОЙСТВА:")
    add_line(f"  Плотность ρ(P,T) = {data.get('density', '—')} кг/м³")
    add_line(f"  Вязкость μ(P,T) = {data.get('viscosity', '—')} мПа·с")
    add_line(f"  Теплоёмкость Cp = {data.get('cp', '—')} кДж/(кг·К)")
    add_line(f"  Теплопроводность λ = {data.get('lambda', '—')} Вт/(м·К)")
    add_line(f"  Влагосодержание W = {data.get('water', '—')} г/м³")
    
    # 5. Эффект Джоуля-Томсона
    add_line("")
    add_line("ЭФФЕКТ ДЖОУЛЯ-ТОМСОНА:")
    add_line(f"  Коэффициент Джоуля-Томсона Di = {data.get('Di', '—')} К/МПа")
    add_line(f"  Перепад температуры ΔT = {data.get('delta_T', '—')} К")
    add_line(f"  Конечная температура T₂ = {data.get('T2', '—')} К ({data.get('T2_C', '—')} °C)")
    
    
    
    c.save()
    buffer.seek(0)
    
    return send_file(buffer, download_name='report_gas_calculator.pdf', as_attachment=True, mimetype='application/pdf')

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
