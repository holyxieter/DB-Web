from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import mysql.connector

# 设置数据库连接
Mysql = mysql.connector.connect(
    host='localhost',
    user='root',
    passwd='1234',
    database='wmdb'
)

app = Flask(__name__)
app.secret_key = 'chwhcn#21&vjv'

order_ids = ['O016', 'O017', 'O018', 'O019', 'O020', 'O021', 'O022', 'O023', 'O024', 'O025']


@app.route('/')
def login():
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def do_login():
    username = request.form['username']
    password = request.form['password']

    if not username or not password:
        flash('用户名或密码不能为空')
        return redirect(url_for('login'))

    cursor = Mysql.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_registration WHERE username = %s AND password = %s", (username, password))
    user_registration = cursor.fetchone()
    cursor.close()

    if user_registration:
        user_type = user_registration['user_type']
        uid = user_registration['uid']

        cursor = Mysql.cursor(dictionary=True)

        if user_type == 'customer':
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (uid,))
        elif user_type == 'DBA':
            cursor.execute("SELECT * FROM dbat WHERE dba_id = %s", (uid,))
        elif user_type == 'delivery':
            cursor.execute("SELECT * FROM delivery WHERE delivery_id = %s", (uid,))

        user_details = cursor.fetchone()
        cursor.close()

        if user_details:
            # 合并 user_registration 和 user 表的信息
            user_info = {**user_registration, **user_details}
            session['user'] = user_info

            if user_type == 'customer':
                return redirect(url_for('order'))
            elif user_type == 'DBA':
                return redirect(url_for('back'))
            elif user_type == 'delivery':
                return redirect(url_for('delivery'))
        else:
            flash('用户信息不完整，请联系管理员')
            return redirect(url_for('login'))
    else:
        flash('用户名或密码错误')
        return redirect(url_for('login'))


@app.route('/order')
def order():
    if 'user' in session:
        user_info = session['user']
        return render_template('order.html', user=user_info)
    else:
        return redirect(url_for('login'))


@app.route('/api/food_items')
def food_items():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM dish")
        food_items = cursor.fetchall()
        cursor.execute("SELECT * FROM setmeal")
        meal_items = cursor.fetchall()
        cursor.close()

        result = {
            'food_items': food_items,
            'meal_items': meal_items
        }

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/submit_order', methods=['POST'])
def submit_order():
    if 'user' not in session:
        return jsonify({'error': 'User not logged in'}), 403

    user_info = session['user']
    user_id = user_info['user_id']
    name = user_info['name']
    phone = user_info['phone']
    order_data = request.json.get('order')

    if not order_data:
        return jsonify({'error': 'No order data provided'}), 400

    try:
        with Mysql.cursor() as cursor:
            # 查询用户地址
            address_sql = "SELECT * FROM address WHERE user_id = %s"
            cursor.execute(address_sql, (user_id,))
            address = cursor.fetchone()
            if not address:
                return jsonify({'error': 'Address not found for user'}), 400
            address_str = ", ".join(address[2:6])

            # 插入订单数据到 Order 表中
            order_id = order_ids.pop(0)
            sql = """
                INSERT INTO `order` (order_id, order_status, user_id, user_name, order_time, phone, address)
                VALUES (%s, 0, %s, %s, NOW(), %s, %s)
            """
            cursor.execute(sql, (order_id, user_id, name, phone, address_str))

            # 解析 order_data 并插入购物清单表
            total_price = 0
            for item in order_data:
                name = item['name']
                quantity = item['quantity']

                # 查询 dish 表
                cursor.execute("SELECT dish_id, price FROM dish WHERE name = %s", (name,))
                dish_result = cursor.fetchone()

                if dish_result:
                    # 如果在 dish 表中找到，插入到 shopping_list 表
                    dish_id = dish_result[0]
                    price = dish_result[1]
                    cursor.execute("""
                        INSERT INTO shopping_list (order_id, dish_id, dish_number)
                        VALUES (%s, %s, %s)
                    """, (order_id, dish_id, quantity))
                    total_price += quantity * price
                    # 更新菜品销售量
                    sql_update = "UPDATE dish SET sales = sales + %s WHERE dish_id = %s"
                    cursor.execute(sql_update, (quantity, dish_id))

                else:
                    # 如果在 dish 表中没有找到，查询 setmeal 表
                    cursor.execute("SELECT setmeal_id, price FROM setmeal WHERE name = %s", (name,))
                    setmeal_result = cursor.fetchone()

                    if setmeal_result:
                        # 如果在 setmeal 表中找到，插入到 shopping_list 表
                        setmeal_id = setmeal_result[0]
                        price = setmeal_result[1]
                        cursor.execute("""
                            INSERT INTO shopping_list (order_id, setmeal_id, setmeal_number)
                            VALUES (%s, %s, %s)
                        """, (order_id, setmeal_id, quantity))
                        total_price += quantity * price
                        # 更新套餐销售量
                        sql_update = "UPDATE setmeal SET sales = sales + %s WHERE setmeal_id = %s"
                        cursor.execute(sql_update, (quantity, setmeal_id))

                        # 更新套餐包含的菜品销售量
                        relation_sql = "SELECT dish_id, dish_numbers FROM relation WHERE setmeal_id = %s"
                        cursor.execute(relation_sql, (setmeal_id,))
                        dishes = cursor.fetchall()
                        for dish in dishes:
                            dishid = dish[0]
                            dishn = dish[1]
                            sql_update = "UPDATE dish SET sales = sales + %s WHERE dish_id = %s"
                            cursor.execute(sql_update, (dishn, dishid))

            # 更新订单金额
            sql = "UPDATE `order` SET order_amount = %s WHERE order_id = %s"
            cursor.execute(sql, (total_price + 5, order_id))

            Mysql.commit()
            print("Transaction committed successfully.")

        return jsonify({'message': 'Order submitted successfully!', 'order_id': order_id})
    except Exception as e:
        Mysql.rollback()
        print(f"Exception occurred: {str(e)}")
        return jsonify({'error': f"Exception: {str(e)}"}), 500


@app.route('/delivery')
def delivery():
    if 'user' in session:
        user_info = session['user']
        return render_template('delivery.html', user=user_info)
    else:
        return redirect(url_for('login'))


@app.route('/api/order_items')
def order_items():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM `order` WHERE order_status = 0")
        order_items = cursor.fetchall()
        cursor.close()
        return jsonify(order_items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/take_order', methods=['POST'])
def take_order():
    if 'user' not in session:
        return jsonify({'error': 'User not logged in'}), 403

    user_info = session['user']
    delivery_id = user_info['delivery_id']
    order_id = request.json.get('order_id')

    if not order_id:
        return jsonify({'error': 'No order data provided'}), 400

    try:
        with Mysql.cursor() as cursor:
            # 更新订单的配送状态和外卖员
            sql = "UPDATE `order` SET deliver_id = %s ,order_status = %s WHERE order_id = %s"
            cursor.execute(sql, (delivery_id, 1, order_id))
            Mysql.commit()
            print("Transaction committed successfully.")
        return jsonify({'message': 'Order submitted successfully!', 'order_id': order_id})
    except Exception as e:
        Mysql.rollback()
        print(f"Exception occurred: {str(e)}")
        return jsonify({'error': f"Exception: {str(e)}"}), 500


@app.route('/back')
def back():
    if 'user' in session:
        user_info = session['user']
        return render_template('back.html', user=user_info)
    else:
        return redirect(url_for('login'))


@app.route('/api/order_show')
def order_show():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM `order`")
        order_data = cursor.fetchall()
        cursor.close()
        return jsonify(order_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/dishes_show')
def dishes_show():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM dish")
        dish_data = cursor.fetchall()
        cursor.close()
        return jsonify(dish_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_dish', methods=['POST'])
def update_dish():
    dish_data = request.get_json()
    dish_id = dish_data.get('id')
    name = dish_data.get('name')
    price = dish_data.get('price')
    description = dish_data.get('description')

    sql = """UPDATE dish SET name = %s, price = %s, description = %s WHERE dish_id = %s"""
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (name, price, description, dish_id))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_dish', methods=['POST'])
def add_dish():
    dish_data = request.get_json()

    dish_id = dish_data.get('菜品ID')
    name = dish_data.get('菜品名称')
    price = dish_data.get('价格')
    img = dish_data.get('图片路径')
    description = dish_data.get('菜品描述')
    chef_id = dish_data.get('负责厨师')

    sql = """INSERT INTO dish (dish_id, name, price, image, description, chef_id, sales) VALUES (%s, %s, %s, %s, %s, %s, 0)"""
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (dish_id, name, price, img, description, chef_id))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_dish', methods=['POST'])
def delete_dish():
    dish_data = request.get_json()
    dish_id = dish_data.get('dish_id')
    sql = "DELETE FROM dish WHERE dish_id = %s"
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (dish_id,))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/setmeal_show')
def setmeal_show():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM setmeal")
        setmeal_data = cursor.fetchall()
        cursor.close()
        return jsonify(setmeal_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_setmeal', methods=['POST'])
def update_setmeal():
    setmeal_data = request.get_json()
    setmeal_id = setmeal_data.get('id')
    name = setmeal_data.get('name')
    price = setmeal_data.get('price')
    description = setmeal_data.get('description')

    sql = """UPDATE setmeal SET name = %s, price = %s, description = %s WHERE setmeal_id = %s"""
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (name, price, description, setmeal_id))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_setmeal', methods=['POST'])
def add_setmeal():
    setmeal_data = request.get_json()

    setmeal_id = setmeal_data.get('套餐ID')
    name = setmeal_data.get('套餐名称')
    price = setmeal_data.get('价格')
    img = setmeal_data.get('图片路径')
    description = setmeal_data.get('套餐描述')

    sql = """INSERT INTO setmeal (setmeal_id, name, price, image, description, sales) VALUES (%s, %s, %s, %s, %s, 0)"""
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (setmeal_id, name, price, img, description))
            Mysql.commit()
            return jsonify({'message': 'Setmeal updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_setmeal', methods=['POST'])
def delete_setmeal():
    setmeal_data = request.get_json()
    setmeal_id = setmeal_data.get('setmeal_id')
    sql = "DELETE FROM setmeal WHERE setmeal_id = %s"
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (setmeal_id,))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/relation_show')
def relation_show():
    try:
        cursor = Mysql.cursor(dictionary=True)
        cursor.execute("SELECT * FROM relation")
        relation_data = cursor.fetchall()
        cursor.close()
        return jsonify(relation_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/update_relation', methods=['POST'])
def update_relation():
    relation_data = request.get_json()
    setmeal_id = relation_data.get('setmeal_id')
    dish_id = relation_data.get('dish_id')
    dish_numbers = relation_data.get('dish_numbers')

    sql = "UPDATE relation SET dish_numbers = %s WHERE setmeal_id = %s AND dish_id = %s"
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (dish_numbers, setmeal_id, dish_id))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/add_relation', methods=['POST'])
def add_relation():
    relation_data = request.get_json()

    setmeal_id = relation_data.get('套餐ID')
    setmeal_name = relation_data.get('套餐名称')
    dish_id = relation_data.get('菜品ID')
    dish_name = relation_data.get('菜品名称')
    dish_num = relation_data.get('菜品数量')

    sql = """INSERT INTO relation (setmeal_id, setmeal_name, dish_id, dish_name, dish_numbers) VALUES (%s, %s, %s, %s, %s)"""
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (setmeal_id, setmeal_name, dish_id, dish_name, dish_num))
            Mysql.commit()
            return jsonify({'message': 'Relation updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete_relation', methods=['POST'])
def delete_relation():
    relation_data = request.get_json()
    setmeal_id = relation_data.get('setmeal_id')
    dish_id = relation_data.get('dish_id')
    print(relation_data)

    sql = "DELETE FROM relation WHERE setmeal_id = %s AND dish_id = %s"
    try:
        with Mysql.cursor() as cursor:
            cursor.execute(sql, (setmeal_id, dish_id))
            Mysql.commit()
            return jsonify({'message': 'Dish updated successfully'}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/show_delivery_salary')
def show_delivery_salary():
    try:
        cursor = Mysql.cursor(dictionary=True)
        sql = """   SELECT deliver_id, COUNT(*) as total_orders
                    FROM `Order`
                    WHERE order_time BETWEEN '2024-06-01 00:00:00' AND '2024-06-14 23:59:59'
                    AND deliver_id IS NOT NULL
                    GROUP BY deliver_id;
        """
        cursor.execute(sql)
        temp = cursor.fetchall()

        for record in temp:
            deliver_id = record['deliver_id']
            total_orders = record['total_orders']
            per = total_orders * 10
            sql = "UPDATE delivery_salary SET real_pay = %s, percentage = %s WHERE delivery_id = %s AND issue_date = '2024-06-14'"
            cursor.execute(sql, (3000 + per, per, deliver_id))
        Mysql.commit()

        cursor.execute("SELECT * FROM delivery_salary")
        salary_data = cursor.fetchall()
        cursor.close()
        return jsonify(salary_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/show_chef_salary')
def show_chef_salary():
    try:
        cursor = Mysql.cursor(dictionary=True)
        # 步骤一：获取六月份所有订单ID
        query_order_ids = (
            "SELECT order_id "
            "FROM `Order` "
            "WHERE order_time BETWEEN '2024-06-14 00:00:00' AND '2024-06-14 23:59:59'"
        )
        cursor.execute(query_order_ids)
        rows = cursor.fetchall()
        order_ids = [row['order_id'] for row in rows]

        # 步骤二：获取六月份订单中的所有菜品和套餐ID
        dish_setmeal_ids = set()
        for order_id in order_ids:
            query_dish_setmeal_ids = (
                "SELECT dish_id, setmeal_id "
                "FROM shopping_list "
                "WHERE order_id = %s"
            )
            cursor.execute(query_dish_setmeal_ids, (order_id,))
            rows = cursor.fetchall()
            for row in rows:
                dish_id = row.get('dish_id')
                setmeal_id = row.get('setmeal_id')
                if dish_id is not None:
                    dish_setmeal_ids.add(dish_id)
                if setmeal_id is not None:
                    dish_setmeal_ids.add(setmeal_id)

        # 区分菜品ID和套餐ID
        dish_ids = {id_ for id_ in dish_setmeal_ids if id_.startswith('d')}
        setmeal_ids = {id_ for id_ in dish_setmeal_ids if id_.startswith('t')}

        # 步骤三：从套餐关系表中获取套餐包含的菜品ID
        extra_dish_ids_from_setmeals = set()
        for setmeal_id in setmeal_ids:
            query_extra_dish_ids = (
                "SELECT dish_id "
                "FROM relation "
                "WHERE setmeal_id = %s"
            )
            cursor.execute(query_extra_dish_ids, (setmeal_id,))
            extra_dish_rows = cursor.fetchall()
            for row in extra_dish_rows:
                extra_dish_ids_from_setmeals.add(row['dish_id'])

        # 合并套餐中解析出的菜品ID到原来的集合中
        dish_ids.update(extra_dish_ids_from_setmeals)

        # 步骤四：根据菜品ID查询厨师ID和菜品数量
        chef_dish_counts = {}
        for dish_id in dish_ids:
            query_chef_id = (
                "SELECT chef_id "
                "FROM dish "
                "WHERE dish_id = %s"
            )
            cursor.execute(query_chef_id, (dish_id,))
            chef_id = cursor.fetchone()['chef_id']
            if chef_id not in chef_dish_counts:
                chef_dish_counts[chef_id] = 1
            else:
                chef_dish_counts[chef_id] += 1

        for chef_id in chef_dish_counts:
            total_orders = chef_dish_counts[chef_id]
            per = total_orders * 150
            sql = "UPDATE chef_salary SET real_pay = %s, percentage = %s WHERE chef_id = %s AND issue_date = '2024-06-14'"
            cursor.execute(sql, (5000 + per, per, chef_id))
        Mysql.commit()

        cursor.execute("SELECT * FROM chef_salary")
        salary_data = cursor.fetchall()
        cursor.close()
        return jsonify(salary_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
