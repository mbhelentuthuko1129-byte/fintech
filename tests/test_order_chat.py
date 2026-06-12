from app.services.order_chat import (
    Intent,
    ParsedItem,
    parse_customer_command,
    parse_items,
    parse_owner_command,
    resolve_items,
)

PRODUCTS = [
    {"id": "p1", "name": "White Bread", "sku": "WB1", "price": 22.50},
    {"id": "p2", "name": "Brown Bread", "sku": "BB1", "price": 24.00},
    {"id": "p3", "name": "Milk 2L", "sku": "MLK", "price": 38.00},
]


class TestParseItems:
    def test_qty_x_name(self):
        assert parse_items("2x bread") == [ParsedItem(name="bread", quantity=2)]

    def test_qty_space_name(self):
        assert parse_items("3 eggs") == [ParsedItem(name="eggs", quantity=3)]

    def test_name_x_qty(self):
        assert parse_items("bread x2") == [ParsedItem(name="bread", quantity=2)]

    def test_bare_name_defaults_to_one(self):
        assert parse_items("milk") == [ParsedItem(name="milk", quantity=1)]

    def test_comma_and_and_separators(self):
        items = parse_items("2x bread, milk and 3 eggs")
        assert items == [
            ParsedItem(name="bread", quantity=2),
            ParsedItem(name="milk", quantity=1),
            ParsedItem(name="eggs", quantity=3),
        ]


class TestCustomerCommands:
    def test_catalog_words(self):
        for word in ("catalog", "menu", "Prices"):
            assert parse_customer_command(word).intent == Intent.CATALOG

    def test_greeting_is_help(self):
        assert parse_customer_command("hi").intent == Intent.HELP

    def test_status_with_order_number(self):
        cmd = parse_customer_command("status ORD-12")
        assert cmd.intent == Intent.STATUS
        assert cmd.order_number == "ORD-12"

    def test_status_normalises_order_number(self):
        assert parse_customer_command("status ord 12").order_number == "ORD-12"

    def test_order_command(self):
        cmd = parse_customer_command("order 2x white bread, 1x milk 2l")
        assert cmd.intent == Intent.ORDER
        assert cmd.items[0] == ParsedItem(name="white bread", quantity=2)

    def test_bare_order_word_is_help(self):
        assert parse_customer_command("order").intent == Intent.HELP

    def test_free_text_is_unknown(self):
        assert parse_customer_command("can I get two loaves please").intent == Intent.UNKNOWN


class TestOwnerCommands:
    def test_add_product(self):
        cmd = parse_owner_command("add product White Bread 22.50")
        assert cmd.intent == Intent.ADD_PRODUCT
        assert cmd.product_name == "White Bread"
        assert cmd.price == 22.50

    def test_add_product_with_rand_prefix_and_comma(self):
        cmd = parse_owner_command("add product Milk 2L R38,00")
        assert cmd.intent == Intent.ADD_PRODUCT
        assert cmd.price == 38.00

    def test_list_orders(self):
        assert parse_owner_command("orders").intent == Intent.LIST_ORDERS

    def test_fulfil_variants(self):
        for text in ("fulfil ORD-3", "fulfill ord 3", "done ORD-3"):
            cmd = parse_owner_command(text)
            assert cmd.intent == Intent.FULFIL
            assert cmd.order_number == "ORD-3"

    def test_cancel(self):
        cmd = parse_owner_command("cancel ORD-7")
        assert cmd.intent == Intent.CANCEL
        assert cmd.order_number == "ORD-7"

    def test_owner_falls_back_to_customer_commands(self):
        assert parse_owner_command("catalog").intent == Intent.CATALOG


class TestResolveItems:
    def test_exact_name(self):
        resolved, unresolved = resolve_items([ParsedItem("white bread", 2)], PRODUCTS)
        assert resolved == [(PRODUCTS[0], 2)] and not unresolved

    def test_sku_match(self):
        resolved, _ = resolve_items([ParsedItem("MLK", 1)], PRODUCTS)
        assert resolved == [(PRODUCTS[2], 1)]

    def test_unique_substring(self):
        resolved, unresolved = resolve_items([ParsedItem("milk", 1)], PRODUCTS)
        assert resolved == [(PRODUCTS[2], 1)] and not unresolved

    def test_ambiguous_substring_is_unresolved(self):
        # "bread" matches both white and brown bread — must not guess.
        resolved, unresolved = resolve_items([ParsedItem("bread", 1)], PRODUCTS)
        assert not resolved and unresolved == ["bread"]

    def test_unknown_product(self):
        _, unresolved = resolve_items([ParsedItem("caviar", 1)], PRODUCTS)
        assert unresolved == ["caviar"]
