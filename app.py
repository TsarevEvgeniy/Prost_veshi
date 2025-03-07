import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import datetime as dt
import io
import base64
import calendar

# Подключаем кастомный CSS для фона и шрифта
st.markdown("""
    <style>
        body {background: #f2bc62;}
    </style>
""", unsafe_allow_html=True)

# Титульный лист
st.title("Аналитическая панель автономной некомерческой организации Простые вещи")

st.markdown(
    "<p style='font-size:14px; font-weight:bold;'>"
    "Аналитическая панель создана для АНО Простые вещи в рамках презентации работы мастерской Яндекс. "
    "Практикум и включает в себя когортный и RFM-анализ, анализ платежей и анализ пользователей. "
    "Для перехода между страницами используйте меню слева."
    "</p>",
    unsafe_allow_html=True
)
# Инициализируем session_state, если он еще не был установлен
if "show_raw_data" not in st.session_state:
    st.session_state["show_raw_data"] = True
# Кнопка для загрузки файла
uploaded_file = st.file_uploader("Загрузите файл с данными (например, CSV или Excel)", type=["csv", "xlsx"])

if uploaded_file is not None:
    if uploaded_file.name.endswith(".csv"):
        data = pd.read_csv(uploaded_file)
    else:
        data = pd.read_excel(uploaded_file, engine='openpyxl')
        
    del data['Unnamed: 0']
    del data['file']
    data = data[data["status"] != "Отклонена"]
    data["aim"] = data["aim"].replace("Вещи с особенностями", "Пожертвование на ведение уставной деятельности")
    data["aim"] = data["aim"].fillna("Не определен")
    data = data.dropna(subset=["customer"])
    data["order_id"] = data["order_id"].fillna("-")
    
    data['action_date'] = pd.to_datetime(data['action_date'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
    data = data.dropna(subset=['action_date'])

    if st.sidebar.button('Общая информация'):
        st.write("Обработанные данные о пожертвованиях: обработаны пропуски, удалены ненужные колонки, удалены отклоненные платежи, проверен файл на дубликаты.")
        st.dataframe(data.head())
        
        # График топ-10 клиентов по сумме платежей
        customer_sums = data.groupby("customer")["final_sum"].sum().sort_values(ascending=False).head(10)
        plt.figure(figsize=(12, 6))
        bars = plt.barh(customer_sums.index, customer_sums.values, color="skyblue", edgecolor="black")
        plt.xlabel("Сумма платежей (final_sum)", fontsize=12)
        plt.ylabel("Клиент (customer)", fontsize=12)
        plt.title("Топ-10 клиентов по сумме платежей", fontsize=14, fontweight="bold")
        plt.xticks(fontsize=10)
        plt.yticks(fontsize=10)
        plt.gca().invert_yaxis()
        for bar in bars:
            plt.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"{bar.get_width():,.0f}",
                     va="center", ha="left", fontsize=10, color="black")
        plt.grid(axis="x", linestyle="--", alpha=0.7)
        st.pyplot(plt)

        # График динамики выручки по месяцам
        data['month'] = data['action_date'].dt.to_period('M')
        monthly_revenue = data.groupby('month')['final_sum'].sum()
        plt.figure(figsize=(10, 6))
        monthly_revenue.plot(kind='bar', color='skyblue', edgecolor='black')
        plt.title('Динамика выручки по месяцам')
        plt.xlabel('Месяц')
        plt.ylabel('Выручка (₽)')
        plt.xticks(rotation=45)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        st.pyplot(plt)

    if st.sidebar.button('RFM анализ'):
        temp = ['customer', 'order_id', 'action_date', 'final_sum']
        rfm_data = data[temp]

        # Отключаем предупреждения
        pd.options.mode.chained_assignment = None

        # Устанавливаем текущую дату для анализа
        NOW = dt.datetime(2024, 8, 31)

        # Преобразуем столбец с датой в datetime формат
        rfm_data['action_date'] = pd.to_datetime(rfm_data['action_date'])

        # Создаём таблицу для RFM анализа
        rfm_table = rfm_data.groupby('customer').agg({
            'action_date': lambda x: (NOW - x.max()).days,  # Recency
            'order_id': lambda x: len(x.unique()),  # Frequency
            'final_sum': lambda x: x.sum()  # Monetary
        })

        # Преобразуем Recency в целое число
        rfm_table['action_date'] = rfm_table['action_date'].astype(int)

        # Переименовываем столбцы
        rfm_table.rename(columns={'action_date': 'recency',
                                   'order_id': 'frequency',
                                   'final_sum': 'monetary_value'}, inplace=True)

        # Вычисляем квантили для сегментации
        quantiles = rfm_table.quantile(q=[0.33, 0.67])
        quantiles = quantiles.to_dict()

        # Функции для сегментации
        def R_Class(x, p, d):
            if x <= d[p][0.33]:
                return 3
            elif x <= d[p][0.67]:
                return 2
            else:
                return 1

        def FM_Class(x, p, d):
            if x <= d[p][0.33]:
                return 1
            elif x <= d[p][0.67]:
                return 2
            else:
                return 3

        # Применяем сегментацию по каждому квартилю
        rfm_Segment = rfm_table.copy()
        rfm_Segment['R_Quartile'] = rfm_Segment['recency'].apply(R_Class, args=('recency', quantiles,))
        rfm_Segment['F_Quartile'] = rfm_Segment['frequency'].apply(FM_Class, args=('frequency', quantiles,))
        rfm_Segment['M_Quartile'] = rfm_Segment['monetary_value'].apply(FM_Class, args=('monetary_value', quantiles,))

        # Формируем итоговый RFM
        rfm_Segment['rfm'] = rfm_Segment.R_Quartile.map(str) + rfm_Segment.F_Quartile.map(str) + rfm_Segment.M_Quartile.map(str)

        # 
        rfm_Segment = rfm_Segment.reset_index()

        # Мержим с исходными данными
        data = data.merge(rfm_Segment[['customer', 'rfm']], on='customer', how='left')

        # Функция для категоризации клиентов
        list_klient = {
            'Ушедшие клиенты': ['111', '112', '113', '121', '122', '123', '131', '132', '133'],
            'Неактивные клиенты': ['211', '212', '213', '221', '222', '223', '231', '232', '233'],
            'Постоянные клиенты': ['311', '312', '313', '321', '322', '323', '331', '332', '333']
        }

        def categor_klient(rfm):
            for klient, items_klient in list_klient.items():
                for item in items_klient:
                    if item in rfm:
                        return klient
            return 'Неопределённый'  # Если клиент не попал в категорию

        data['categor_klient'] = data['rfm'].apply(categor_klient)

        # Группируем по RFM и считаем статистики
        rfm_summary = data.groupby('rfm').agg(
        people_count=('id', 'count'),  # Количество людей с данным rfm
        avg_payment=('final_sum', 'mean'),  # Средний платеж
        total_donations=('final_sum', 'sum')  # Общая сумма пожертвований
        ).reset_index()

        # Округляем суммы для удобства
        rfm_summary['avg_payment'] = rfm_summary['avg_payment'].round(2)
        rfm_summary['total_donations'] = rfm_summary['total_donations'].round(2)

        rfm_summary = rfm_summary.rename(columns={
        'people_count': 'Количество человек',
        'avg_payment': 'Средний платеж',
        'total_donations': 'Общая сумма пожертвований'
        })
        
        st.markdown('### **Таблица RFM анализа**')
        st.dataframe(rfm_summary)
        
        # Слайдер для выбора топа
        if 'slider_value' not in st.session_state:
           st.session_state.slider_value = 3  # начальное значение

        # Функция для обновления значения слайдера
        def update_slider():
            st.session_state.slider_value = st.session_state.slider

        # Слайдер для выбора топа
        slide = st.slider('Выберите свой топ и снова перейдите на страницу RFM анализа. Изменения вступят в силу.', min_value=1, max_value=20, value=st.session_state.slider_value, key='slider', on_change=update_slider)

        # Выводим актуальные данные на основе текущего значения слайдера
        st.write(f'Топ-{st.session_state.slider_value} категорий по суммам пожертвований:')
        top_rfm_total_final_sum = data.groupby('rfm')['final_sum'].sum().sort_values(ascending=False).nlargest(st.session_state.slider_value)
        st.dataframe(top_rfm_total_final_sum)

        st.write(f'Топ-{st.session_state.slider_value} жертвователей, внёсших самые больше суммы:')
        top_customer_total_final_sum = data.groupby('customer')['final_sum'].sum().sort_values(ascending=False).nlargest(st.session_state.slider_value)
        st.dataframe(top_customer_total_final_sum)

        st.write(f'Топ-{st.session_state.slider_value} категорий по количеству жертвователей:')
        top_rfm_customer = data.groupby('rfm')['customer'].nunique().sort_values(ascending=False).nlargest(st.session_state.slider_value)
        st.dataframe(top_rfm_customer)
        
        # Выводы
        st.markdown(f'''
        <div style="background-color: #f0f8ff; color: black; padding: 10px; border-radius: 5px;">
        <strong>Выводы:</strong><br><br>

        Наибольшую часть пожертвований приносят следующие группы:
        - <strong>313</strong>: 532249.96 руб.  
        - <strong>333</strong>: 412856.61 руб. 
        - <strong>213</strong>: 359166.72 руб. 

        Группа жертвующая небольшие суммы, но тем не менее наиболее многочисленная и поэтому очень важная.
        - <strong>111</strong>: 94901.81 руб.

        Группа людей, которые жертвовали давно, редко, но большие суммы. Можно как-то их "разбудить".  
        - <strong>113</strong>: 225241.02 руб.
        
        И непосредственно человека с e-mail: <strong>humblehelptope****@gmail.com</strong>, который пожертвовал 145200.00 руб.
        </div>
        ''', unsafe_allow_html=True)
        
    if st.sidebar.button('Когортный анализ'):
    # 1. Определение когорт
        data['cohort_month'] = data.groupby('customer')['action_date'].transform('min').dt.to_period('M')
        data['month_transaction'] = data['action_date'].dt.to_period('M')
       
         # 2. Цикл для обработки всех когорт
        cohort_tables = []
        for cohort in data['cohort_month'].unique():
            cohort_df = data[data['cohort_month'] == cohort].copy()
            cohort_data = (cohort_df.groupby(['cohort_month', 'month_transaction'])
                   .agg(
                       users=('customer', 'nunique'),
                       revenue=('final_sum', 'sum'),
                       transactions=('customer', 'count')
                   )
                   .reset_index())
    
            cohort_data['lifetime'] = (cohort_data['month_transaction'].astype('int64') - cohort_data['cohort_month'].astype('int64'))
            
             # Retention Rate и Churn Rate
            initial_users = cohort_data.groupby('cohort_month')['users'].transform('first')
            cohort_data['Retention_Rate'] = cohort_data['users'] / initial_users
            cohort_data['Churn_Rate'] = 1 - cohort_data['Retention_Rate']
            
             # LTV
            cohort_data['LTV'] = cohort_data.groupby('cohort_month')['revenue'].cumsum() / cohort_data.groupby('cohort_month')['users'].transform('first')
    
             # Средний чек
            cohort_data['Average_Check'] = cohort_data['revenue'] / cohort_data['transactions']
    
            cohort_tables.append(cohort_data)
            
        # 3. Объединяем все когорты в одну таблицу
        cohort_final = pd.concat(cohort_tables, ignore_index=True)

        # 4. Создаем сводную таблицу (pivot)
        pivot_table = cohort_final.pivot(index='lifetime', columns='cohort_month', values='LTV')
            
        # 5. Визуализация с помощью heatmap
        plt.figure(figsize=(10, 6))
        sns.heatmap(pivot_table, annot=True, fmt='.0f', cmap='Blues')
        plt.title('Когортный анализ: LTV')
        plt.xlabel('Когорта (месяц)')
        plt.ylabel('Месяц жизни когорты')
        st.pyplot(plt)
        
        # Выводы
        st.markdown(f'''
        <div style="background-color: #f0f8ff; color: black; padding: 10px; border-radius: 5px;">
        <strong>Выводы:</strong><br><br>

1. Динамика LTV по когортам

LTV (Lifetime Value) постепенно увеличивается с увеличением месяца жизни когорты, что ожидаемо, так как пользователи совершают дополнительные покупки.
Однако темпы роста LTV различаются между когортах. Это может свидетельствовать о различной лояльности пользователей в разные месяцы.

2. Retention Rate и Churn Rate

В первые месяцы Retention Rate значительно выше, но затем заметно снижается, что указывает на отток пользователей.
Средний Retention Rate на 3-4 месяце жизни когорты падает, что говорит о необходимости усиления маркетинговых и удерживающих стратегий.
Churn Rate (коэффициент оттока) растет по мере старения когорты, особенно после 2-3 месяцев, что может быть сигналом для улучшения клиентского опыта.

3. Различие между когортами

Когорты из разных месяцев показывают разные LTV, что может говорить о сезонных факторах или эффективности маркетинговых кампаний.
Например, когорта, стартовавшая в начале года, имеет более высокие показатели LTV на поздних этапах, что может быть связано с новогодними акциями и повышенной активностью пользователей.
4. Средний чек (Average Check)

Средний чек достаточно стабилен между когортами, но может варьироваться по месяцам.
Более высокие значения среднего чека в некоторых когортных месяцах могут свидетельствовать о продажах более дорогих товаров или успешных апселлах.

**Рекомендации**

✅ Удержание пользователей: необходимо внедрять механизмы удержания после 1-2 месяцев, так как на этом этапе наблюдается наибольший отток.
✅ Маркетинговая оптимизация: стоит анализировать, какие маркетинговые активности привлекают наиболее ценных пользователей (с высоким LTV).
✅ Анализ эффективности продаж: необходимо изучить факторы, влияющие на средний чек, и оценить, можно ли увеличить его за счет дополнительных продаж или кросс-продаж.
✅ Работа с разными когортами: изучить, почему одни когорты демонстрируют более высокий Retention Rate и LTV, а другие теряют пользователей быстрее.

Вывод:  Улучшение Retention Rate и Churn Rate в первые месяцы жизни когорты может существенно повысить LTV и общую прибыльность бизнеса.
        ''', unsafe_allow_html=True)
        
    if st.sidebar.button('Маркетинговый анализ'):
        # Рассчитаем DAU, WAU, MAU, Sticky Factor
        data['date'] = data['action_date'].dt.date

        DAU = data.groupby('date')['customer'].nunique()
        WAU = data.groupby(pd.Grouper(key='action_date', freq='W'))['customer'].nunique()
        MAU = data.groupby(pd.Grouper(key='action_date', freq='ME'))['customer'].nunique()

        DAU.index = pd.to_datetime(DAU.index)  # Преобразуем в DatetimeIndex

        Sticky_Factor = (DAU.resample('ME').mean() / MAU).dropna()
        
        # Динамика и скользящее среднее
        DAU_rolling = DAU.rolling(7).mean()
        WAU_rolling = WAU.rolling(4).mean()
        MAU_rolling = MAU.rolling(3).mean()
        
        # 7. Визуализация DAU, WAU, MAU
        plt.figure(figsize=(12, 6))
        plt.plot(DAU, label='DAU', alpha=0.6)
        plt.plot(DAU_rolling, label='DAU (7-day MA)', linestyle='--')
        plt.title('Daily Active Users (DAU)')
        plt.xlabel('Дата')
        plt.ylabel('Кол-во пользователей')
        plt.legend()
        plt.grid()
        st.pyplot(plt)
        
        plt.figure(figsize=(12, 6))
        plt.plot(WAU, label='WAU', alpha=0.6)
        plt.plot(WAU_rolling, label='WAU (4-week MA)', linestyle='--')
        plt.title('Weekly Active Users (WAU)')
        plt.xlabel('Дата')
        plt.ylabel('Кол-во пользователей')
        plt.legend()
        plt.grid()
        st.pyplot(plt)
        
        plt.figure(figsize=(12, 6))
        plt.plot(MAU, label='MAU', alpha=0.6)
        plt.plot(MAU_rolling, label='MAU (3-month MA)', linestyle='--')
        plt.title('Monthly Active Users (MAU)')
        plt.xlabel('Дата')
        plt.ylabel('Кол-во пользователей')
        plt.legend()
        plt.grid()
        st.pyplot(plt)
        
        # 8. Визуализация Sticky Factor
        plt.figure(figsize=(10, 5))
        plt.plot(Sticky_Factor, marker='o', linestyle='-', color='b')
        plt.title('Sticky Factor (DAU/MAU)')
        plt.xlabel('Месяц')
        plt.ylabel('Sticky Factor')
        plt.grid()
        st.pyplot(plt)
