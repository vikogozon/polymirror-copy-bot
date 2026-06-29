# CopyPoly Single Wallet Copier

Bot minimo para copiar una sola wallet de Polymarket:

```text
0x204f72f35326db932158cba6adff0b9a1da95e14
```

## Comandos

Chequeo live sin enviar orden:

```powershell
python -m copypoly.cli live-check
```

Ver posiciones locales copiadas:

```powershell
python -m copypoly.cli paper-status
```

Una sola vuelta:

```powershell
python -u -m copypoly.cli copy-wallet --once
```

Bot continuo:

```powershell
python -u -m copypoly.cli copy-wallet
```

`python -u -m copypoly.cli run` es alias del mismo copiador.

## Configuracion

La configuracion vive en `.env`.

Las variables principales son:

```text
MODE=live
WATCHLIST_WALLETS=0x204f72f35326db932158cba6adff0b9a1da95e14
START_AFTER_TIMESTAMP=...
MAX_MARKET_USDC=5
POSITION_PERCENT=0.01
```

Para empezar desde cero, actualiza `START_AFTER_TIMESTAMP` al momento actual antes de arrancar.

## Modo sin limites de copia

La configuracion live actual copia cada BUY/SELL nuevo del trader sin limites
de presupuesto, mercado, numero de compras, antiguedad ni proteccion de precio:

```text
TRADE_LOOKBACK_SECONDS=0
BLOCK_OPPOSITE_BUYS=false
MAX_TRADE_USDC=0
MAX_MARKET_USDC=0
MAX_MARKET_BUYS=0
MAX_TOTAL_OPEN_USDC=0
MAX_OPEN_POSITIONS=0
DAILY_MAX_USDC=0
ENFORCE_LIVE_PRICE_PROTECTION=false
```

`0` significa sin limite. Todavia pueden impedir una orden el saldo insuficiente,
la falta de liquidez, el minimo del mercado o un error/restriccion de Polymarket.
