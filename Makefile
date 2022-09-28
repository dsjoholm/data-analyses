# Run this in data-analyses
# To specify different Makefile: make build_parallel_corridors -f Makefile
build_competitive_corridors:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/competitive_corridors/ -rf
	#need git rm because otherwise, just local removal, but git change is untracked
	python portfolio/portfolio.py clean competitive_corridors
	python bus_service_increase/deploy_portfolio_yaml.py   
	python portfolio/portfolio.py build competitive_corridors --deploy 
	git add portfolio/competitive_corridors/district_*/ portfolio/competitive_corridors/*.yml portfolio/competitive_corridors/*.md 
	git add portfolio/sites/ 
    #--config=./portfolio/test-analyses.yml


build_100_recs:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/one_hundred_recs/ -rf
	#python portfolio/portfolio.py clean one_hundred_recs
	python portfolio/portfolio.py build one_hundred_recs --deploy 
	git add portfolio/one_hundred_recs/*.ipynb portfolio/one_hundred_recs/*.yml portfolio/one_hundred_recs/*.md 
	git add portfolio/sites/ 
    #--config=./portfolio/test-analyses.yml


build_dla_reports:
	pip install -r portfolio/requirements.txt
	git rm portfolio/dla/ -rf
	python portfolio/portfolio.py build dla --deploy 
	git add portfolio/dla/district_*/ portfolio/dla/*.yml portfolio/dla/*.md 
	git add portfolio/sites/dla.yml


build_hqta:
	pip install -r portfolio/requirements.txt
	git rm portfolio/hqta/ -rf
	python portfolio/portfolio.py clean hqta
	python portfolio/portfolio.py build hqta --deploy 
	git add portfolio/hqta/*.yml portfolio/hqta/*.md portfolio/hqta/*.ipynb
	git add portfolio/sites/ 
    
add_precommit:
	pip install pre-commit
	pre-commit install 
	#pre-commit run --all-files 
