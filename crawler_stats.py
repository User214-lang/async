import time
from collections import defaultdict
from typing import Dict, Optional
from urllib.parse import urlparse
import json
from datetime import datetime 

class CrawlerStats:

    def __init__(self):
        self.start_time = time.monotonic()
        self.end_time: Optional[float] = None
        self.total_processed = 0
        self.successful_requests = 0
        self.failed_requests = 0

        self.status_code_distribution = defaultdict(int)
        self.domain_counts = defaultdict(int)
        self.total_response_time = 0.0

    def record_success(self, url: str, status_code: int, response_time: float) -> None:
        self.total_processed += 1
        self.successful_requests += 1
        self.status_code_distribution[status_code] += 1
        self._add_domain(url)
        self.total_response_time += response_time

    def record_failure(self, url: str, error_type: str) -> None:
        self.total_processed += 1
        self.failed_requests += 1
        self.status_code_distribution['error'] += 1
        self._add_domain(url)

    def _add_domain(self, url: str) -> None:
        domain = urlparse(url).netloc
        if domain:
            self.domain_counts[domain] += 1

    def finish(self) -> None:
        self.end_time = time.monotonic()

    @property
    def duration(self) -> float:
        if self.end_time is None:
            return time.monotonic() - self.start_time
        return self.end_time - self.start_time

    @property
    def average_speed(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.total_processed / self.duration

    @property
    def avg_response_time(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests

    def get_top_domains(self, limit: int = 10) -> list:
        #топ n доменов по количеству страниц
        return sorted(self.domain_counts.items(), key=lambda x: x[1], reverse=True)[:limit]

    def get_stats(self) -> dict:
        return {
            'total_processed': self.total_processed,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'duration': self.duration,
            'average_speed': self.average_speed,
            'avg_response_time': self.avg_response_time,
            'status_code_distribution': dict(self.status_code_distribution),
            'top_domains': self.get_top_domains(),
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None
        }

    def print_stats(self) -> None:
        stats = self.get_stats()
        print("\nРасширенная статистика краулера:")
        print(f"Всего обработано страниц: {stats['total_processed']}")
        print(f"Успешных запросов: {stats['successful_requests']}")
        print(f"Неудачных запросов: {stats['failed_requests']}")
        print(f"Время работы: {stats['duration']:.2f} с")
        print(f"Средняя скорость: {stats['average_speed']:.2f} стр/с")
        print(f"Среднее время ответа: {stats['avg_response_time']:.3f} с")
        
        print("\nРаспределение по статус-кодам:")
        for code, count in sorted(stats['status_code_distribution'].items(), key=lambda x: str(x[0])):
            print(f"  {code}: {count}")
        
        print("\nТоп доменов по количеству страниц:")
        for domain, count in stats['top_domains']:
            print(f"  {domain}: {count}")

    def export_to_json(self, filename: str) -> None:
        stats = self.get_stats()
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"Статистика экспортирована в {filename}")

    def export_to_html_report(self, filename: str) -> None:
        stats = self.get_stats()
        
        status_items = sorted(
            [(str(k), v) for k, v in stats['status_code_distribution'].items()],
            key=lambda x: x[1], reverse=True
        )
        max_status_count = max([v for _, v in status_items], default=1)
        
        top_domains = stats['top_domains']
        max_domain_count = max([count for _, count in top_domains], default=1)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Отчёт краулера</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f9f9f9; padding: 15px; border-radius: 6px; text-align: center; border-left: 4px solid #4CAF50; }}
        .stat-card .value {{ font-size: 28px; font-weight: bold; color: #333; }}
        .stat-card .label {{ font-size: 14px; color: #777; margin-top: 5px; }}
        .bar-container {{ margin: 10px 0; }}
        .bar-label {{ display: flex; justify-content: space-between; font-size: 14px; }}
        .bar {{ background: #4CAF50; height: 20px; border-radius: 4px; transition: width 0.3s; }}
        .bar-wrapper {{ background: #e0e0e0; border-radius: 4px; overflow: hidden; }}
        .bar-domain {{ background: #2196F3; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 8px 12px; border: 1px solid #ddd; text-align: left; }}
        th {{ background: #4CAF50; color: white; }}
        tr:nth-child(even) {{ background: #f9f9f9; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #aaa; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Отчёт о работе краулера</h1>
        <p><strong>Дата генерации:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{stats['total_processed']}</div>
                <div class="label">Всего обработано</div>
            </div>
            <div class="stat-card" style="border-left-color: #4CAF50;">
                <div class="value">{stats['successful_requests']}</div>
                <div class="label">Успешных запросов</div>
            </div>
            <div class="stat-card" style="border-left-color: #f44336;">
                <div class="value">{stats['failed_requests']}</div>
                <div class="label">Неудачных запросов</div>
            </div>
            <div class="stat-card" style="border-left-color: #FF9800;">
                <div class="value">{stats['average_speed']:.2f}</div>
                <div class="label">Средняя скорость (стр/с)</div>
            </div>
            <div class="stat-card" style="border-left-color: #9C27B0;">
                <div class="value">{stats['avg_response_time']:.3f}</div>
                <div class="label">Среднее время ответа (с)</div>
            </div>
            <div class="stat-card" style="border-left-color: #3F51B5;">
                <div class="value">{stats['duration']:.2f}</div>
                <div class="label">Время работы (с)</div>
            </div>
        </div>
        
        <h2>Распределение по статус-кодам</h2>
        <div>
"""
        for code, count in status_items:
            width = (count / max_status_count * 100) if max_status_count > 0 else 0
            html += f"""
            <div class="bar-container">
                <div class="bar-label"><span>{code}</span><span>{count}</span></div>
                <div class="bar-wrapper"><div class="bar" style="width: {width:.1f}%;"></div></div>
            </div>
"""
        html += """
        </div>
        
        <h2>Топ доменов по количеству страниц</h2>
        <div>
"""
        for domain, count in top_domains:
            width = (count / max_domain_count * 100) if max_domain_count > 0 else 0
            html += f"""
            <div class="bar-container">
                <div class="bar-label"><span>{domain}</span><span>{count}</span></div>
                <div class="bar-wrapper"><div class="bar bar-domain" style="width: {width:.1f}%;"></div></div>
            </div>
"""
        html += """
        </div>
        
        <h2>Детальная статистика</h2>
        <table>
            <tr><th>Показатель</th><th>Значение</th></tr>
            <tr><td>Всего обработано</td><td>{}</td></tr>
            <tr><td>Успешных запросов</td><td>{}</td></tr>
            <tr><td>Неудачных запросов</td><td>{}</td></tr>
            <tr><td>Средняя скорость</td><td>{:.2f} стр/с</td></tr>
            <tr><td>Среднее время ответа</td><td>{:.3f} с</td></tr>
            <tr><td>Время работы</td><td>{:.2f} с</td></tr>
            <tr><td>Начало работы</td><td>{}</td></tr>
            <tr><td>Окончание работы</td><td>{}</td></tr>
        </table>
        
        <div class="footer">
            Отчёт создан автоматически. Данные собраны во время работы краулера.
        </div>
    </div>
</body>
</html>
""".format(
    stats['total_processed'],
    stats['successful_requests'],
    stats['failed_requests'],
    stats['average_speed'],
    stats['avg_response_time'],
    stats['duration'],
    stats['start_time'],
    stats['end_time'] if stats['end_time'] else 'не завершён'
)

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"HTML-отчёт сохранён в {filename}")