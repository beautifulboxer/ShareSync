CREATE DATABASE IF NOT EXISTS sharesync;
USE sharesync;

create table users(
userid INT primary key auto_increment,
name varchar(100) NOT NULL,
email varchar(100) UNIQUE NOT NULL,
password varchar(260) NOT NULL
);