import os
import sys
import time
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Ошибка: DATABASE_URL не задан!")

print(f"Подключение к БД: {DATABASE_URL}")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

class Customer(Base):
    __tablename__ = 'Customers'
    CustomerID = Column(Integer, primary_key=True, autoincrement=True)
    FirstName = Column(String(100), nullable=False)
    LastName = Column(String(100), nullable=False)
    Email = Column(String(150), unique=True, nullable=False)

class Product(Base):
    __tablename__ = 'Products'
    ProductID = Column(Integer, primary_key=True, autoincrement=True)
    ProductName = Column(String(100), nullable=False)
    Price = Column(Float, nullable=False)

class Order(Base):
    __tablename__ = 'Orders'
    OrderID = Column(Integer, primary_key=True, autoincrement=True)
    CustomerID = Column(Integer, ForeignKey('Customers.CustomerID'), nullable=False)
    OrderDate = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    TotalAmount = Column(Float, default=0.0)

class OrderItem(Base):
    __tablename__ = 'OrderItems'
    OrderItemID = Column(Integer, primary_key=True, autoincrement=True)
    OrderID = Column(Integer, ForeignKey('Orders.OrderID'), nullable=False)
    ProductID = Column(Integer, ForeignKey('Products.ProductID'), nullable=False)
    Quantity = Column(Integer, nullable=False)
    Subtotal = Column(Float, nullable=False)

def init_db():
    try:
        Base.metadata.create_all(engine)
        print("Таблицы созданы/проверены.")
    except Exception as e:
        print(f"Ошибка создания таблиц: {e}")
        sys.exit(1)

def scenario1(customer_id: int, items: list[dict]):
    session = SessionLocal()
    try:
        new_order = Order(CustomerID=customer_id)
        session.add(new_order)
        session.flush()

        total = 0.0
        for item in items:
            prod = session.execute(select(Product).where(Product.ProductID == item['ProductID'])).scalar_one()
            subtotal = prod.Price * item['Quantity']
            session.add(OrderItem(OrderID=new_order.OrderID, ProductID=item['ProductID'], Quantity=item['Quantity'], Subtotal=subtotal))
            total += subtotal

        new_order.TotalAmount = total
        session.commit()
        print(f"Сценарий 1: Заказ {new_order.OrderID} создан. Сумма: {total}")
    except Exception as e:
        session.rollback()
        print(f"Сценарий 1: {e}")
    finally:
        session.close()

def scenario2(customer_id: int, new_email: str):
    session = SessionLocal()
    try:
        customer = session.execute(select(Customer).where(Customer.CustomerID == customer_id)).scalar_one()
        customer.Email = new_email
        session.commit()
        print(f"Сценарий 2: Email клиента {customer_id} обновлен.")
    except Exception as e:
        session.rollback()
        print(f"Сценарий 2: {e}")
    finally:
        session.close()

def scenario3(product_name: str, price: float):
    session = SessionLocal()
    try:
        new_product = Product(ProductName=product_name, Price=price)
        session.add(new_product)
        session.commit()
        print(f"Сценарий 3: Продукт '{product_name}' добавлен.")
    except Exception as e:
        session.rollback()
        print(f"Сценарий 3: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    init_db()

    with SessionLocal() as session:
        try:
            if not session.execute(select(Customer).where(Customer.CustomerID == 1)).first():
                session.add(Customer(FirstName="Test", LastName="User", Email="test@mail.com"))
                session.add(Product(ProductName="Laptop", Price=1500.0))
                session.commit()
                print("Тестовые данные созданы.")
        except Exception as e:
            session.rollback()
            print(f"Ошибка тестовых данных: {e}")

    scenario3("Phone", 700.0)
    scenario1(1, [{"ProductID": 1, "Quantity": 1}, {"ProductID": 2, "Quantity": 2}])
    scenario2(1, "updated@mail.com")