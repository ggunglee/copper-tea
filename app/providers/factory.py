from app.config import Settings
from app.providers.base import FundamentalsProvider, MarketDataProvider, NewsProvider
from app.providers.csv_provider import CsvFundamentalsProvider, CsvMarketDataProvider, CsvNewsProvider
from app.providers.mock_provider import MockFundamentalsProvider, MockMarketDataProvider, MockNewsProvider
from app.providers.rss_news_provider import RssNewsProvider
from app.providers.yahoo_provider import YahooFundamentalsProvider, YahooMarketDataProvider


def market_data_provider(settings: Settings) -> MarketDataProvider:
    if settings.price_provider == "yahoo":
        return YahooMarketDataProvider()
    if settings.price_provider == "csv":
        return CsvMarketDataProvider()
    return MockMarketDataProvider()


def news_provider(settings: Settings) -> NewsProvider:
    if settings.news_provider == "rss":
        return RssNewsProvider()
    if settings.news_provider == "csv":
        return CsvNewsProvider()
    return MockNewsProvider()


def fundamentals_provider(settings: Settings) -> FundamentalsProvider:
    if settings.fundamentals_provider == "yahoo":
        return YahooFundamentalsProvider()
    if settings.fundamentals_provider == "csv":
        return CsvFundamentalsProvider()
    return MockFundamentalsProvider()
