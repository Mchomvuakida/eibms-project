from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.main_dashboard, name='main_dashboard'),
    path('clerk/', views.clerk_dashboard, name='clerk_dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/add/', views.expense_create, name='expense_create'),
    path('productions/', views.production_list, name='production_list'),
    path('productions/add/', views.production_create, name='production_create'),
    path('sales/add/', views.sale_create, name='sale_create'),
    path('sales/', views.sale_list, name='sale_list'),
    path('sales/<int:sale_id>/', views.sale_detail, name='sale_detail'),
    path('trucks/profitability/', views.truck_profitability, name='truck_profitability'),
    path('trucks/profitability/<int:truck_id>/', views.truck_profitability, name='truck_profit_detail'),
    path('trucks/', views.truck_list, name='truck_list'),
    path('trips/add/', views.trip_create, name='trip_create'),
    path('reports/tra-expenses/', views.tra_expense_report, name='tra_expense_report'),
    path('reports/sales/', views.sales_report, name='sales_report'),
    path('customers/overdue/', views.overdue_customers, name='overdue_customers'),
    path('reports/profit-loss/', views.profit_and_loss, name='profit_and_loss'),
    path('stock/purchase/', views.stock_purchase, name='stock_purchase'),
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_create, name='customer_create'),
    path('customers/<int:customer_id>/repayment/', views.customer_repayment, name='customer_repayment'),
]