import json


def sauvegarder(stock):

    with open(
        "ancien_stock.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            stock,
            f,
            indent=4,
            ensure_ascii=False
        )


    print(
        "💾 ancien_stock.json mis à jour"
    )
