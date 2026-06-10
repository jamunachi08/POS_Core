.PHONY: build dev install clean

# Build the cashier SPA into alphax_pos_suite/alphax_pos_suite/public/dist/cashier/
build:
	cd frontend && npm install && npm run build

# Run the Vite dev server (proxies /api to localhost:8000)
dev:
	cd frontend && npm run dev

install:
	cd frontend && npm install

clean:
	rm -rf alphax_pos_suite/alphax_pos_suite/public/dist/cashier
	rm -rf frontend/node_modules
