"""
Модуль для создания графиков и визуализации данных питания
"""
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import pandas as pd
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
import io
import os
from clients.supabase_client import supabase

# Настройка стиля графиков
plt.style.use('default')
sns.set_palette("husl")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 12
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3

def get_weight_data(user_id: int, days: int = 30) -> List[Dict]:
    """Получает данные веса за последние N дней"""
    try:
        start_date = date.today() - timedelta(days=days)
        res = supabase.table("Nutrition Bot").select("date, weight") \
            .eq("user_id", str(user_id)) \
            .gte("date", str(start_date)) \
            .not_.is_("weight", "null") \
            .order("date", desc=False) \
            .execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"❌ Failed to get weight data: {e}")
        return []

def get_nutrition_data(user_id: int, days: int = 7) -> List[Dict]:
    """Получает данные питания за последние N дней"""
    try:
        start_date = date.today() - timedelta(days=days)
        
        # Получаем данные по дням
        daily_data = []
        for i in range(days + 1):
            current_date = start_date + timedelta(days=i)
            
            # Суммируем питание за день
            res = supabase.table("meals").select("calories, protein, fat, carbs") \
                .eq("user_id", str(user_id)) \
                .eq("date", str(current_date)) \
                .execute()
            
            if res.data:
                total = {"calories": 0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
                for meal in res.data:
                    total["calories"] += meal.get("calories", 0)
                    total["protein"] += meal.get("protein", 0)
                    total["fat"] += meal.get("fat", 0)
                    total["carbs"] += meal.get("carbs", 0)
                
                total["date"] = str(current_date)
                daily_data.append(total)
            else:
                daily_data.append({
                    "date": str(current_date),
                    "calories": 0,
                    "protein": 0,
                    "fat": 0,
                    "carbs": 0
                })
        
        return daily_data
    except Exception as e:
        print(f"❌ Failed to get nutrition data: {e}")
        return []

def get_steps_data(user_id: int, days: int = 7) -> List[Dict]:
    """Получает данные шагов за последние N дней"""
    try:
        start_date = date.today() - timedelta(days=days)
        res = supabase.table("Nutrition Bot").select("date, steps") \
            .eq("user_id", str(user_id)) \
            .gte("date", str(start_date)) \
            .order("date", desc=False) \
            .execute()
        return res.data if res.data else []
    except Exception as e:
        print(f"❌ Failed to get steps data: {e}")
        return []

def create_weight_chart(user_id: int, days: int = 30) -> Optional[str]:
    """Создает график изменения веса"""
    try:
        data = get_weight_data(user_id, days)
        if len(data) < 2:
            return None
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Основная линия веса
        ax.plot(df['date'], df['weight'], 
                marker='o', linewidth=2.5, markersize=6,
                color='#2E86AB', label='Вес')
        
        # Тренд
        z = np.polyfit(range(len(df)), df['weight'], 1)
        p = np.poly1d(z)
        ax.plot(df['date'], p(range(len(df))), 
                linestyle='--', alpha=0.7, color='#A23B72', label='Тренд')
        
        # Оформление
        ax.set_title(f'📉 Динамика веса за {days} дней', fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Дата', fontsize=12)
        ax.set_ylabel('Вес (кг)', fontsize=12)
        
        # Форматирование дат на оси X
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days//7)))
        plt.xticks(rotation=45)
        
        # Сетка и легенда
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=10)
        
        # Статистика
        weight_change = df['weight'].iloc[-1] - df['weight'].iloc[0]
        change_text = f"Изменение: {weight_change:+.1f} кг"
        ax.text(0.02, 0.98, change_text, transform=ax.transAxes, 
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))
        
        plt.tight_layout()
        
        # Сохраняем во временный файл
        filename = f"temp_weight_{user_id}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        return filename
        
    except Exception as e:
        print(f"❌ Failed to create weight chart: {e}")
        return None

def create_calories_chart(user_id: int, days: int = 7) -> Optional[str]:
    """Создает график калорий за неделю"""
    try:
        data = get_nutrition_data(user_id, days)
        if not data:
            return None
        
        # Создаем DataFrame
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Получаем целевые калории пользователя
        from clients.supabase_client import get_user_targets
        targets = get_user_targets(user_id)
        target_calories = targets.get('calories', 2000)
        
        # Создаем график
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Столбчатая диаграмма калорий
        bars = ax.bar(df['date'], df['calories'], 
                     color=['#FF6B6B' if cal > target_calories else '#4ECDC4' 
                           for cal in df['calories']],
                     alpha=0.8, edgecolor='white', linewidth=1)
        
        # Линия цели
        ax.axhline(y=target_calories, color='#FFD93D', linestyle='--', 
                  linewidth=2, label=f'Цель: {target_calories} ккал')
        
        # Оформление
        ax.set_title(f'🔥 Калории за {days} дней', fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Дата', fontsize=12)
        ax.set_ylabel('Калории', fontsize=12)
        
        # Форматирование дат
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        plt.xticks(rotation=45)
        
        # Подписи на столбцах
        for bar, cal in zip(bars, df['calories']):
            if cal > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 20,
                       f'{int(cal)}', ha='center', va='bottom', fontsize=9)
        
        # Статистика
        avg_calories = df['calories'].mean()
        stats_text = f"Среднее: {avg_calories:.0f} ккал/день"
        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))
        
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=10)
        plt.tight_layout()
        
        # Сохраняем
        filename = f"temp_calories_{user_id}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        return filename
        
    except Exception as e:
        print(f"❌ Failed to create calories chart: {e}")
        return None

def create_macros_chart(user_id: int, days: int = 7) -> Optional[str]:
    """Создает круговую диаграмму БЖУ"""
    try:
        data = get_nutrition_data(user_id, days)
        if not data:
            return None
        
        # Суммируем БЖУ за период
        total_protein = sum(d['protein'] for d in data)
        total_fat = sum(d['fat'] for d in data)
        total_carbs = sum(d['carbs'] for d in data)
        
        if total_protein + total_fat + total_carbs == 0:
            return None
        
        # Конвертируем в калории
        protein_cal = total_protein * 4
        fat_cal = total_fat * 9
        carbs_cal = total_carbs * 4
        
        # Данные для диаграммы
        labels = ['Белки', 'Жиры', 'Углеводы']
        sizes = [protein_cal, fat_cal, carbs_cal]
        colors = ['#FF9999', '#66B2FF', '#99FF99']
        
        # Создаем график
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Круговая диаграмма
        wedges, texts, autotexts = ax1.pie(sizes, labels=labels, colors=colors,
                                          autopct='%1.1f%%', startangle=90,
                                          textprops={'fontsize': 11})
        
        ax1.set_title(f'🥗 Баланс БЖУ за {days} дней\n(в калориях)', 
                     fontsize=14, fontweight='bold', pad=20)
        
        # Столбчатая диаграмма в граммах
        gram_data = [total_protein, total_fat, total_carbs]
        bars = ax2.bar(labels, gram_data, color=colors, alpha=0.8)
        
        ax2.set_title('Макронутриенты (граммы)', fontsize=14, fontweight='bold')
        ax2.set_ylabel('Граммы', fontsize=12)
        
        # Подписи на столбцах
        for bar, grams in zip(bars, gram_data):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                    f'{grams:.0f}г', ha='center', va='bottom', fontsize=10)
        
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Сохраняем
        filename = f"temp_macros_{user_id}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        return filename
        
    except Exception as e:
        print(f"❌ Failed to create macros chart: {e}")
        return None

def create_activity_chart(user_id: int, days: int = 7) -> Optional[str]:
    """Создает график активности (шаги + калории)"""
    try:
        steps_data = get_steps_data(user_id, days)
        if not steps_data:
            return None
        
        # Подготавливаем данные
        df = pd.DataFrame(steps_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        df['steps'] = df['steps'].fillna(0)
        
        # Получаем вес пользователя для расчета калорий
        from clients.supabase_client import get_user_profile
        profile = get_user_profile(user_id)
        weight = profile['weight'] if profile else 70
        
        # Рассчитываем калории от шагов
        df['calories_from_steps'] = df['steps'] * weight * 0.00035
        
        # Создаем график с двумя осями Y
        fig, ax1 = plt.subplots(figsize=(12, 6))
        
        # График шагов
        color1 = '#1f77b4'
        ax1.set_xlabel('Дата', fontsize=12)
        ax1.set_ylabel('Шаги', color=color1, fontsize=12)
        bars1 = ax1.bar(df['date'], df['steps'], alpha=0.7, color=color1, label='Шаги')
        ax1.tick_params(axis='y', labelcolor=color1)
        
        # Вторая ось для калорий
        ax2 = ax1.twinx()
        color2 = '#ff7f0e'
        ax2.set_ylabel('Калории от шагов', color=color2, fontsize=12)
        line2 = ax2.plot(df['date'], df['calories_from_steps'], 
                        color=color2, marker='o', linewidth=2, label='Калории')
        ax2.tick_params(axis='y', labelcolor=color2)
        
        # Оформление
        ax1.set_title(f'👣 Активность за {days} дней', fontsize=16, fontweight='bold', pad=20)
        
        # Форматирование дат
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        plt.xticks(rotation=45)
        
        # Подписи на столбцах шагов
        for bar, steps in zip(bars1, df['steps']):
            if steps > 0:
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 100,
                        f'{int(steps):,}', ha='center', va='bottom', fontsize=9)
        
        # Статистика
        avg_steps = df['steps'].mean()
        total_calories = df['calories_from_steps'].sum()
        stats_text = f"Среднее: {avg_steps:.0f} шагов/день\nВсего сожжено: {total_calories:.0f} ккал"
        ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
                fontsize=11, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))
        
        ax1.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Сохраняем
        filename = f"temp_activity_{user_id}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close()
        
        return filename
        
    except Exception as e:
        print(f"❌ Failed to create activity chart: {e}")
        return None

def cleanup_temp_files(user_id: int):
    """Удаляет временные файлы графиков"""
    temp_files = [
        f"temp_weight_{user_id}.png",
        f"temp_calories_{user_id}.png", 
        f"temp_macros_{user_id}.png",
        f"temp_activity_{user_id}.png"
    ]
    
    for filename in temp_files:
        try:
            if os.path.exists(filename):
                os.remove(filename)
        except Exception as e:
            print(f"⚠️ Failed to delete temp file {filename}: {e}")

# Добавляем недостающий импорт
import numpy as np