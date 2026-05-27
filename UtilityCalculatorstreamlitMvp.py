import streamlit as st

st.set_page_config(
    page_title="Калькулятор коммуналки в Латвии",
    page_icon="🏠",
    layout="centered",
)

st.title("🏠 Калькулятор коммуналки для арендаторов")
st.caption("MVP-версия: вводишь аренду, площадь, счётчики и тарифы — получаешь примерную месячную стоимость.")

st.info(
    "Расчёт приблизительный. Тарифы и расходы вводятся вручную, потому что они отличаются по дому, району, сезону и поставщику."
)

#Базовые данные

st.header("1. Данные квартиры")

col1,col2 = st.columns(2)

with col1:
    rent = st.number_input(
        "Аренда, €/мес",
        min_value=0.0,
        value=450.0,
        step=10.0,
    )

    area = st.number_input(
        "Площадь, м²",
        min_value=1.0,
        value=45.0,
        step=1.0,
    )

with col2:
    people = st.number_input(
        "Количество жильцов",
        min_value=1,
        value=2,
        step=1,
    )

    deposit = st.number_input(
        "Депозит, €",
        min_value=0.0,
        value=450.0,
        step=10.0,
    )

#Домовый расходы

st.header("2. Домовые расходы")

management_fee_per_m2= st.number_input(
    "Обслуживание дома / apsaimniekošana, €/м²",
    min_value=0.0,
    value=0.80,
    step=0.05,
)

heating_mode = st.radio(
    "Как считать отопление?",
    ["По общей сумме", "По €/м²"],
    horizontal=True,
)

if heating_mode == "по общей сумме":
    heating_total = st.number_input(
        "Отопление, €/мес",
        min_value=0.0,
        value=90.0,
        step=5.0,
    )
else:
    heating_per_m2 = st.number_input(
        "Отопление, €/м²",
        min_value=0.0,
        value=2.00,
        step=0.10,
    )
    heating_total = heating_per_m2 * area

waste = st.number_input(
    "Вывоз мусора, €/мес",
    min_value=0.0,
    value=8.0,
    step=1.0,
)

other_house_costs = st.number_input(
    "Другие домовые расходы, €/мес",
    min_value=0.0,
    value=0.0,
    step=1.0,
)

#Счетчики и услуги

st.header("3. счётчики и услуги")

st.subheader("Элекстричество")
electricity_kwh = st.number_input(
    "Потребление эекстричества, кВт⋅ч",
    min_value=0.0,
    value=150.0,
    step=5.0,
)
electricity_tariff = st.number_input(
    "Тариф электричества, €/кВт⋅ч",
    min_value=0.0,
    value=0.25,
    step=5.0,
)

st.subheader("Вода")
col3, col4 = st.columns(2)

with col3:
    cold_water_m3 = st.number_input(
        "Холодная вода, м³",
        min_value=0.0,
        value=5.0,
        step=0.5,
    )

    cold_water_tariff = st.number_input(
        "Тариф холодной воды, €/м³",
        min_value=0.0,
        value=2.00,
        step=0.10,
    )

with col4:
    hot_water_m3 = st.number_input(
        "Горячая вода, м³",
        min_value=0.0,
        value=3.0,
        step=0.5,
    )

    hot_water_tariff = st.number_input(
        "Тариф горячей воды, €/м³",
        min_value=0.0,
        value=6.00,
        step=0.10,
    )

internet = st.number_input(
    "Интернет / TV, €/мес",
    min_value=0.0,
    value=20.0,
    step=1.0,
)

other_services = st.number_input(
    "Другие услуги, €/мес",
    min_value=0.0,
    value=0.0,
    step=1.0,
)

# Расчёты

management_total = management_fee_per_m2 * area
electricity_total = electricity_kwh * electricity_tariff
cold_water_total = cold_water_m3 * cold_water_tariff
hot_water_total = hot_water_m3 * hot_water_tariff

utilites_total = (
    management_total
    + heating_total
    + waste
    + other_house_costs
    + electricity_total
    + cold_water_total
    + hot_water_total
    + internet
    + other_services
)

monthly_total = rent + utilites_total
per_person = monthly_total / people
per_m2 = monthly_total / area
first_month_total = monthly_total + deposit

# Результаты

st.header("4. Результат")

metric_col1, metric_col2, metric_col3 = st.columns(3)

metric_col1.metric("Итого в месяц", f"{monthly_total:.2f} €")
metric_col2.metric("На человека", f"{per_person:.2f} €")
metric_col3.metric("За м²", f"{per_m2:.2f} €")

st.metric("Первый месяц с депозитом", f"{first_month_total:.2f} €")

st.subheader("Разбивка расходов")

cost_rows = [
    ("Аренда", rent),
    ("Обслуживание дома", management_total),
    ("вывоз мусора", waste),
    ("Домовые доп. расходы", other_house_costs),
    ("Электричество", electricity_total),
    ("Холодная вода", cold_water_total),
    ("Горячая вода", hot_water_total),
    ("Интернет / TV", internet),
    ("Другие услуги", other_services),
]

for name, amount in cost_rows:
    if amount > 0:
        st.write(f"**{name}:** {amount:.2f} €")

st.divider()

if monthly_total <= 500:
    st.success("Квартира выглядт бюджетной по месячным расходам.")
elif monthly_total <=800:
    st.warning("Расходы средние. стоит внимательно сравнить с похожими вариантами.")
else:
    st.error("Расходы высокие. проверьте отопление, обслуживание дома и депозит.")

