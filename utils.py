import json
import math

# Загрузка справочников
with open('data.json', 'r', encoding='utf-8') as f:
    COMPONENTS = json.load(f)

with open('tables.json', 'r', encoding='utf-8') as f:
    TABLES = json.load(f)


def bilinear_interpolation(x, y, x_values, y_values, Z_table):
    """Билинейная интерполяция по таблице"""
    # Находим индексы
    for i, xv in enumerate(x_values):
        if xv >= x:
            break
    else:
        i = len(x_values) - 1
    
    for j, yv in enumerate(y_values):
        if yv >= y:
            break
    else:
        j = len(y_values) - 1
    
    if i == 0:
        i = 1
    if j == 0:
        j = 1
    
    x1, x2 = x_values[i-1], x_values[i]
    y1, y2 = y_values[j-1], y_values[j]
    
    Z11 = Z_table[i-1][j-1]
    Z21 = Z_table[i][j-1]
    Z12 = Z_table[i-1][j]
    Z22 = Z_table[i][j]
    
    # Интерполяция по x
    Z1 = Z11 + (Z21 - Z11) * (x - x1) / (x2 - x1)
    Z2 = Z12 + (Z22 - Z12) * (x - x1) / (x2 - x1)
    
    # Интерполяция по y
    return Z1 + (Z2 - Z1) * (y - y1) / (y2 - y1)


def calculate_Msm(composition):
    """Молекулярная масса смеси"""
    Msm = 0
    for comp, y in composition.items():
        if comp in COMPONENTS:
            Msm += y * COMPONENTS[comp]['M']
    return round(Msm, 3)


def calculate_relative_density(Msm):
    """Относительная плотность"""
    M_air = 28.96
    return round(Msm / M_air, 3)


def calculate_rho_std(Msm):
    """Плотность при стандартных условиях (кг/м³)"""
    V_std = 24.04
    return round(Msm / V_std, 3)


def calculate_pseudocritical(composition):
    """Псевдокритические параметры по правилу Кэя"""
    P_kr = 0
    T_kr = 0
    omega_cm = 0

    if not composition:
        return 4.6, 190.6, 0.011  # значения по умолчанию для метана
    
    for comp, y in composition.items():
        if comp in COMPONENTS:
            P_kr += y * COMPONENTS[comp]['P_kr']
            T_kr += y * COMPONENTS[comp]['T_kr']
            omega_cm += y * COMPONENTS[comp]['omega']

    if P_kr <= 0:
        P_kr = 4.6
    if T_kr <= 0:
        T_kr = 190.6
    
    return round(P_kr, 3), round(T_kr, 3), round(omega_cm, 3)


def calculate_Z_brown_katz(Ppr, Tpr):
    """Метод 1: Браун-Катц (интерполяция по таблице)"""
    table = TABLES['brown_katz']
    return bilinear_interpolation(
        Ppr, Tpr,
        table['Ppr_values'],
        table['Tpr_values'],
        table['Z_table']
    )
    return round(z, 3) 


def calculate_Z_gurevich(Ppr, Tpr):
    """Метод 2: Гуревич-Латонов (аппроксимация)"""
    z = (0.4 * math.log10(Tpr) + 0.73) ** Ppr + 0.1 * Ppr
    return round(z, 3)


def calculate_Z_two_param(composition, Ppr, Tpr):
    """Метод 3: Двухпараметрический"""
    Z_uv = calculate_Z_brown_katz(Ppr, Tpr)
    
    # Z для неуглеводородов (приближённо)
    Z_N2 = 0.98
    Z_CO2 = 0.95
    Z_H2S = 0.92
    
    y_N2 = composition.get('N2', 0)
    y_CO2 = composition.get('CO2', 0)
    y_H2S = composition.get('H2S', 0)
    y_uv = 1 - y_N2 - y_CO2 - y_H2S
    
    z = Z_uv * y_uv + Z_N2 * y_N2 + Z_CO2 * y_CO2 + Z_H2S * y_H2S
    return round(z, 3)


def solve_cubic_Newton(A, B, max_iter=10, tol=1e-8):
    """Решение кубического уравнения методом Ньютона"""
    Z = 1.0
    for _ in range(max_iter):
        f = Z**3 - (1-B)*Z**2 + (A - 3*B**2 - 2*B)*Z - (A*B - B**2 - B**3)
        f_prime = 3*Z**2 - 2*(1-B)*Z + (A - 3*B**2 - 2*B)
        if abs(f_prime) < 1e-10:
            break
        Z_new = Z - f / f_prime
        if abs(Z_new - Z) < tol:
            return Z_new
        Z = Z_new
    return Z


def calculate_Z_peng_robinson(composition, Ppr, Tpr, omega_cm):
    """Метод 4: Пенг-Робинсон"""
    m = 0.37464 + 1.54226 * omega_cm - 0.26992 * omega_cm**2
    alpha = (1 + m * (1 - math.sqrt(Tpr))) ** 2
    A = 0.45724 * alpha * Ppr / Tpr**2
    B = 0.0778 * Ppr / Tpr
    return round(solve_cubic_Newton(A, B), 3)


def calculate_Z_redlich_kwong(Ppr, Tpr):
    """Метод 5: Редлих-Квонг"""
    A_star = 0.42748 * Ppr / Tpr**2.5
    B_star = 0.08664 * Ppr / Tpr
    
    Z = 1.0
    for _ in range(10):
        f = Z**3 - Z**2 + (A_star - B_star**2 - B_star) * Z - A_star * B_star
        f_prime = 3*Z**2 - 2*Z + (A_star - B_star**2 - B_star)
        if abs(f_prime) < 1e-10:
            break
        Z_new = Z - f / f_prime
        if abs(Z_new - Z) < 1e-8:
            return round(Z_new, 3)
        Z = Z_new
    return round(Z, 3)


def calculate_Z_three_param(composition, Ppr, Tpr, omega_cm):
    """Метод 6: Трёхпараметрический"""
    # Z0 и Z1 из таблиц (упрощённо)
    Z0 = calculate_Z_brown_katz(Ppr, Tpr)
    Z1 = 0.05  # приближённо
    return round(Z0 + omega_cm * Z1, 3)


def calculate_density(P, T, rho_std, Z, P0=0.1013, T_std=293):
    """Плотность газа при P, T"""
    Z0 = 1
    rho = rho_std * P * T_std * Z0 / (Z * P0 * T)
    return round(rho, 3)


def calculate_viscosity(Ppr, Tpr):
    """Вязкость (упрощённо)"""
    mu_atm = 0.0112
    return round(mu_atm * (1 + 0.5 * Ppr), 3)


def calculate_Cp(composition, Msm, Ppr, Tpr):
    """Теплоёмкость"""
    # Cp0
    sum_cp = 0
    for comp, y in composition.items():
        if comp in COMPONENTS:
            sum_cp += y * (COMPONENTS[comp]['M'] ** 0.75)
    Cp0 = 4.3723 * sum_cp / Msm
    
    # ΔCp
    delta_Cp = 32.6 * Ppr / Tpr**4 / Msm
    
    return round(Cp0 + delta_Cp, 3)


def calculate_water_content(P, T):
    """Влагосодержание по формуле Бюкачека"""
    t = T - 273.15
    W0 = (0.467 / P) * math.exp(0.0735 * t - 0.00027 * t**2) + \
         0.418 * math.exp(0.054 * t - 0.0002 * t**2)
    return round(W0, 3)


def calculate_f_Di(Ppr, Tpr):
    """f(Di) по таблице с интерполяцией"""
    table = TABLES['f_Di']
    return bilinear_interpolation(
        Ppr, Tpr,
        table['Ppr_values'],
        table['Tpr_values'],
        table['f_table']
    )


def calculate_joule_thomson(Ppr, Tpr, Cp, P1, P2, T1):
    """Коэффициент Джоуля-Томсона и конечная температура"""
    f_Di = calculate_f_Di(Ppr, Tpr)
    Di = (Tpr * f_Di) / (Ppr * Cp) * 1000  # К/МПа
    
    delta_T = Di * (P1 - P2)
    T2 = T1 - delta_T
    
    return round(Di, 3), round(delta_T, 3), round(T2, 3)
