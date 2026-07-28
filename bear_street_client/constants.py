valid_login_types = {"PASSWORD", "MPIN", "FINGERPRINT"}
valid_sources = {"WEBAPI", "MOBILEAPI"}

valid_exchanges = {"NSE_EQ", "NSE_FO", "NSE_CD", "BSE_EQ", "BSE_FO", "BSE_CD", "MCX", "NCDEX"}

valid_transaction_types = {"BUY", "SELL"}

valid_product_types = {"INTRADAY", "DELIVERY", "BTST", "COVER", "BRACKET", "MTF"}

valid_order_types = {"RL", "RL-MKT", "SL", "SL-MKT"}

valid_validity = {"DAY", "IOC", "GTD", "GTC", "EOS"}

valid_order_statuses = {
    "PENDING", "EXECUTED", "CANCELLED", "OMS_XMITTED", "OMS_REJECT",
    "ORDER_ERROR", "ADMIN_REJECT", "EXCHANGE_XMITTED",
    "AMO_SUBMITTED", "AMO_CANCELLED",
}

valid_position_types = {"daily", "expiry"}
