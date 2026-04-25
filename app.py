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
    
    # Минимальные допустимые значения
    MIN_P = 0.1
    MIN_T = 0.01
    
    if P <= 0 or P is None:
        P = MIN_P
    if T <= 0 or T is None:
        T = MIN_T
    
    if method == 'kay':
        P_kr, T_kr, _ = calculate_pseudocritical(composition)
    else:
        Msm = calculate_Msm(composition)
        rho_bar = calculate_relative_density(Msm)
        P_kr = 4.892 - 0.4048 * rho_bar
        T_kr = 94.717 - 170.8 * rho_bar
    
    # Защита от деления на ноль
    if P_kr <= 0:
        P_kr = 0.1
    if T_kr <= 0:
        T_kr = 0.1
    
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
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    import io
    import datetime
    import os
    
    data = request.json
    
    # Функция безопасного преобразования в float
    def safe_float(value, default=0):
        if value is None or value == '—' or value == '':
            return default
        if isinstance(value, str) and value.strip() == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    # Регистрируем русский шрифт
    font_path = os.path.join(os.path.dirname(__file__), 'shrift', 'DejaVuSans.ttf')
    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
        font_name = 'DejaVuSans'
    else:
        font_name = 'Helvetica'
    
    # Создаём PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4  # 595 x 842
    
    # ========== ЛОГОТИП (верхний правый угол) ==========
    logo_path = os.path.join(os.path.dirname(__file__), 'static', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = ImageReader(logo_path)
            # Размер логотипа: 100x70 пикселей
            c.drawImage(logo, width - 120, height - 105, width=100, height=70, mask='auto')
        except Exception as e:
            print(f"Не удалось загрузить логотип: {e}")
    
    # ========== РИСУЕМ ГРИД (сетку) ==========
    #c.setStrokeColorRGB(0.85, 0.85, 0.85)
    #c.setLineWidth(0.5)
    
    # Вертикальные линии
    #for x in range(50, 550, 50):
    #    c.line(x, 50, x, height - 50)
    # Горизонтальные линии
    #for y in range(50, 800, 50):
    #    c.line(50, y, width - 50, y)
    
    # Рамка
    c.setStrokeColorRGB(0.2, 0.2, 0.5)
    c.setLineWidth(2)
    c.rect(40, 40, width - 80, height - 80)
    c.setLineWidth(1)
    
    # ========== ЗАГОЛОВОК ==========
    c.setFont(font_name, 16)
    c.setFillColorRGB(0, 0, 0.4)
    # Заголовок по центру, левее, чтобы не пересекался с логотипом
    c.drawString(180, height - 60, "ОТЧЁТ О СВОЙСТВАХ ГАЗА")
    c.setFillColorRGB(0, 0, 0)
    
    c.setFont(font_name, 9)
    c.drawString(430, height - 30, f"Дата: {datetime.datetime.now().strftime('%d.%m.%Y')}")
    
    y = height - 95
    
    # ========== 1. СОСТАВ ГАЗА ==========
    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0.5)
    c.drawString(60, y, "1. СОСТАВ ГАЗА")
    c.setFillColorRGB(0, 0, 0)
    y -= 20
    
    c.setFont(font_name, 9)
    composition = data.get('composition', {})
    comp_items = list(composition.items())
    mid = (len(comp_items) + 1) // 2
    for i in range(mid):
        if i < len(comp_items):
            comp, val = comp_items[i]
            c.drawString(70, y, f"{comp}: {safe_float(val)*100:.1f} %")
        if i + mid < len(comp_items):
            comp, val = comp_items[i + mid]
            c.drawString(250, y, f"{comp}: {safe_float(val)*100:.1f} %")
        y -= 16
    y -= 10
    
    # ========== 2. ПАРАМЕТРЫ РАСЧЁТА ==========
    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0.5)
    c.drawString(60, y, "2. ПАРАМЕТРЫ РАСЧЁТА")
    c.setFillColorRGB(0, 0, 0)
    y -= 20

    c.setFont(font_name, 9)

    # Список параметров (левый столбец)
    left_params = [
        ("Давление P", f"{safe_float(data.get('P')):.3f} МПа"),
        ("Температура T", f"{safe_float(data.get('T')):.3f} К"),
        ("Псевдокритическое давление Pкр", f"{safe_float(data.get('P_kr')):.3f} МПа"),
        ("Псевдокритическая температура Tкр", f"{safe_float(data.get('T_kr')):.3f} К"),
        ("Молекулярная масса Mсм", f"{safe_float(data.get('Msm')):.3f} кг/кмоль"),
    ]

    # Список параметров (правый столбец)
    right_params = [
        ("Относительная плотность ρ̅", f"{safe_float(data.get('rho_bar')):.3f}"),
        ("Плотность при ст.усл. ρст", f"{safe_float(data.get('rho_std')):.3f} кг/м³"),
        ("Приведённое давление Pпр", f"{safe_float(data.get('Ppr')):.3f}"),
        ("Приведённая температура Tпр", f"{safe_float(data.get('Tpr')):.3f}"),
    ]

    # Выводим левый столбец
    temp_y = y
    for name, value in left_params:
        c.drawString(70, temp_y, f"{name}: {value}")
        temp_y -= 15

    # Выводим правый столбец
    temp_y = y
    for name, value in right_params:
        c.drawString(310, temp_y, f"{name}: {value}")
        temp_y -= 15

    # Сдвигаем y после всех параметров
    y -= max(len(left_params), len(right_params)) * 15 + 10
    
    # ========== 3. КОЭФФИЦИЕНТ Z ==========
    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0.5)
    c.drawString(60, y, "3. КОЭФФИЦИЕНТ СВЕРХСЖИМАЕМОСТИ Z")
    c.setFillColorRGB(0, 0, 0)
    y -= 20
    
    c.setFont(font_name, 9)
    all_z = data.get('all_Z', {})
    z_methods = [
        ("Метод 1 (Браун-Катц)", all_z.get('method1')),
        ("Метод 2 (Гуревич-Латонов)", all_z.get('method2')),
        ("Метод 3 (Двухпараметрический)", all_z.get('method3')),
        ("Метод 4 (Пенг-Робинсон)", all_z.get('method4')),
        ("Метод 5 (Редлих-Квонг)", all_z.get('method5')),
        ("Метод 6 (Трёхпараметрический)", all_z.get('method6'))
    ]
    
    for i, (name, val) in enumerate(z_methods):
        col = 60 if i < 3 else 310
        row = y - (i % 3) * 16
        c.drawString(col, row, f"{name}: {safe_float(val):.3f}")
    y -= 65
    
    #c.setFont(font_name, 10)
    #c.setFillColorRGB(0.5, 0, 0)
    #c.drawString(60, y, "→ Рекомендуемое значение Z:")
    #c.drawString(220, y, f"{safe_float(data.get('Z')):.3f}")
    #c.setFillColorRGB(0, 0, 0)
    #y -= 30
    
    # ========== 4. ФИЗИЧЕСКИЕ СВОЙСТВА ==========
    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0.5)
    c.drawString(60, y, "4. ФИЗИЧЕСКИЕ СВОЙСТВА")
    c.setFillColorRGB(0, 0, 0)
    y -= 20
    
    c.setFont(font_name, 9)
    props = [
        ("Плотность ρ(P,T)", f"{safe_float(data.get('density')):.3f} кг/м³"),
        ("Вязкость μ(P,T)", f"{safe_float(data.get('viscosity')):.3f} мПа·с"),
        ("Теплоёмкость Cp", f"{safe_float(data.get('cp')):.3f} кДж/(кг·К)"),
        ("Теплопроводность λ", f"{safe_float(data.get('lambda')):.3f} Вт/(м·К)"),
        ("Влагосодержание W", f"{safe_float(data.get('water')):.3f} г/м³")
    ]
    
    for i, (name, value) in enumerate(props):
        c.drawString(70, y, f"{name}: {value}")
        y -= 16
    y -= 10
    
    # ========== 5. ЭФФЕКТ ДЖОУЛЯ-ТОМСОНА ==========
    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0.5)
    c.drawString(60, y, "5. ЭФФЕКТ ДЖОУЛЯ-ТОМСОНА")
    c.setFillColorRGB(0, 0, 0)
    y -= 20
    
    c.setFont(font_name, 9)
    c.drawString(70, y, f"Коэффициент Джоуля-Томсона Di: {safe_float(data.get('Di')):.3f} К/МПа")
    y -= 16
    c.drawString(70, y, f"Перепад температуры ΔT: {safe_float(data.get('delta_T')):.3f} К")
    y -= 16
    c.drawString(70, y, f"Конечная температура T₂: {safe_float(data.get('T2')):.3f} К ({safe_float(data.get('T2_C')):.3f} °C)")
    
    # ========== ПОДПИСЬ ==========
    c.setFont(font_name, 8)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(60, 55, "Расчёт выполнен в «Калькуляторе свойств газа»")
    c.drawString(60, 45, "Филиппова Л. | Бондарь В. | Сынкова Д.")
    
    c.save()
    buffer.seek(0)
    
    return send_file(buffer, download_name='gas_report.pdf', as_attachment=True, mimetype='application/pdf')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
