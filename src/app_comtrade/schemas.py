"""

"""
world_trade = {
    "COMTRADE": {
        "WORLD_TRADE": {
            "v1": {
                "description": "Забираем все данные пришедшие по API",
                "schedule": "1 1 1 28 * *",
                "entityLink": "https://comtradeplus.un.org/TradeFlow",
                "file_type": "parquet",
                "schema": {
                    "type_code": {"type": "String", "null": True},
                    "freq_code": {"type": "String", "null": True},
                    "ref_period_id": {"type": "Int64", "null": True},
                    "ref_year": {
                        "type": "Int64",
                        "null": True,
                        "min": 1984,
                        "max": "year(now())",
                    },
                    "ref_month": {"type": "Int64", "null": True},
                    "period": {"type": "String", "null": True},
                    "reporter_code": {"type": "Int64", "null": True},
                    "reporter_iso": {"type": "String", "null": True},
                    "reporter_desc": {"type": "String", "null": True},
                    "flow_code": {"type": "String", "null": True},
                    "flow_desc": {"type": "String", "null": True},
                    "partner_code": {"type": "Int64", "null": True},
                    "partner_iso": {"type": "String", "null": True},
                    "partner_desc": {"type": "String", "null": True},
                    "partner2_code": {"type": "Int64", "null": True},
                    "partner2_iso": {"type": "String", "null": True},
                    "partner2_desc": {"type": "String", "null": True},
                    "classification_code": {"type": "String", "null": True},
                    "classification_search_code": {"type": "String", "null": True},
                    "is_original_classification": {"type": "Bool", "null": True},
                    "cmd_code": {"type": "String", "null": True},
                    "cmd_desc": {"type": "String", "null": True},
                    "aggr_level": {"type": "Int64", "null": True},
                    "is_leaf": {"type": "Bool", "null": True},
                    "customs_code": {"type": "String", "null": True},
                    "customs_desc": {"type": "String", "null": True},
                    "mos_code": {"type": "String", "null": True},
                    "mot_code": {"type": "String", "null": True},
                    "mot_desc": {"type": "String", "null": True},
                    "qty_unit_code": {"type": "String", "null": True},
                    "qty_unit_abbr": {"type": "String", "null": True},
                    "qty": {"type": "Float64", "null": True},
                    "is_qty_estimated": {"type": "Bool", "null": True},
                    "alt_qty_unit_code": {"type": "String", "null": True},
                    "alt_qty_unit_abbr": {"type": "String", "null": True},
                    "alt_qty": {"type": "Float64", "null": True},
                    "is_alt_qty_estimated": {"type": "Bool", "null": True},
                    "net_wgt": {"type": "Float64", "null": True},
                    "is_net_wgt_estimated": {"type": "Bool", "null": True},
                    "gross_wgt": {"type": "Float64", "null": True},
                    "is_gross_wgt_estimated": {"type": "Bool", "null": True},
                    "cifvalue": {"type": "Float64", "null": True},
                    "fobvalue": {"type": "Float64", "null": True},
                    "primary_value": {"type": "Float64", "null": True},
                    "legacy_estimation_flag": {"type": "Bool", "null": True},
                    "is_reported": {"type": "Bool", "null": True},
                    "is_aggregate": {"type": "Bool", "null": True},
                    "dataset_checksum": {"type": "String", "null": True},
                    "hash_address": {"type": "String", "null": True}
                }
            }
        }
    }
}
