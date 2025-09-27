// API客户端 - 处理HTTP POST请求
class APIClient {
    constructor() {
        this.baseURL = '';
        this.timeout = 10000;
    }

    async request(endpoint, data = {}, method = 'POST') {
        try {
            const response = await fetch(endpoint, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: method !== 'GET' ? JSON.stringify(data) : undefined,
                signal: AbortSignal.timeout(this.timeout)
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    async getStockPrice(symbol, startDate, endDate) {
        return this.request('/api/stock/price', {
            symbol,
            start_date: startDate,
            end_date: endDate
        });
    }

    async getFundamentalData(symbol) {
        return this.request('/api/stock/fundamental', { symbol });
    }

    async getStockNews(symbol, daysBack = 30) {
        return this.request('/api/stock/news', {
            symbol,
            days_back: daysBack
        });
    }

    async sendMessage(message) {
        return this.request('/api/message', message);
    }

    async getHealth() {
        return this.request('/health', {}, 'GET');
    }
}

// 创建全局API客户端实例
window.apiClient = new APIClient();