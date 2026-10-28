def test_create_and_read_item(client):
    payload = {
        "title": "Mechanical Keyboard",
        "description": "RGB mechanical keyboard",
        "price": 89.99,
    }
    create_res = client.post("/api/v1/items/", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["title"] == payload["title"]
    assert data["price"] == payload["price"]
    assert "id" in data

    item_id = data["id"]
    get_res = client.get(f"/api/v1/items/{item_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == item_id


def test_get_nonexistent_item(client):
    res = client.get("/api/v1/items/9999")
    assert res.status_code == 404


def test_create_and_read_user(client):
    payload = {
        "name": "Alex Smith",
        "email": "alex@example.com",
        "password": "securepassword123",
    }
    create_res = client.post("/api/v1/users/", json=payload)
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["name"] == payload["name"]
    assert data["email"] == payload["email"]
    assert "id" in data
    assert "password" not in data


def test_duplicate_user_email(client):
    payload = {
        "name": "Duplicate User",
        "email": "alex@example.com",
        "password": "anotherpassword",
    }
    res = client.post("/api/v1/users/", json=payload)
    assert res.status_code == 400
