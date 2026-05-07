DROP DATABASE IF EXISTS isolation_lab;
CREATE DATABASE isolation_lab;
USE isolation_lab;

CREATE TABLE accounts (
    id INT PRIMARY KEY,
    owner_name VARCHAR(100) NOT NULL,
    balance INT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE orders_demo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    amount INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO accounts (id, owner_name, balance) VALUES
    (1, 'Alice', 1000),
    (2, 'Bob', 1000);

INSERT INTO orders_demo (customer_name, amount) VALUES
    ('Alice', 150),
    ('Alice', 250),
    ('Bob', 300);
