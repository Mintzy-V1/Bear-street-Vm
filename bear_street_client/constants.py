valid_login_types = {"PASSWORD", "MPIN", "FINGERPRINT", "TP_TOKEN"}
valid_second_auth_types = {"OTP", "TOTP", "FINGERPRINT", "REGISTER"}
valid_sources = {"WEBAPI", "MOBILEAPI"}

valid_exchanges = {
    "NSE_EQ", "NSE_FO", "BSE_EQ", "BSE_FO", "MCX_FO", "NCDEX_FO",
    "NSE_CUR", "NSE_COMM", "BSE_CUR", "BSE_COMM", "MSE_CUR", "NSE_OTS",
}

valid_transaction_types = {"BUY", "SELL"}

valid_product_types = {"INTRADAY", "DELIVERY", "BTST", "COVER", "BRACKET", "MTF"}

valid_order_types = {"RL", "RL-MKT", "SL", "SL-MKT"}

valid_validity = {"DAY", "IOC", "GTD", "GTC", "EOS", "EOSESS", "EOTODY"}

valid_order_statuses = {
    "PENDING", "EXECUTED", "CANCELLED", "OMSXMITTED", "OMSREJECT",
    "ORDERERROR", "ADMINREJECT", "EXXMITTED", "AMOACCEPTED", "AMOWITHDRAWN",
}

valid_position_types = {"all", "daily", "expiry"}
