# Run this in data-analyses
# To specify different Makefile: make build_parallel_corridors -f Makefile
build_competitive_corridors:
	pip install -r portfolio/requirements.txt
	#cd bus_service_increase/ && make setup_bus_service_utils && cd ..
	git rm portfolio/competitive_corridors/ -rf
	#need git rm because otherwise, just local removal, but git change is untracked
	python portfolio/portfolio.py clean competitive_corridors
	python bus_service_increase/deploy_portfolio_yaml.py   
	python portfolio/portfolio.py build competitive_corridors --deploy 
	git add portfolio/competitive_corridors/district_*/ portfolio/competitive_corridors/*.yml portfolio/competitive_corridors/*.md 
	git add portfolio/sites/ 
    #--config=./portfolio/test-analyses.yml


build_100_recs:
	#pip install -r portfolio/requirements.txt
	#cd bus_service_increase/ && make setup_bus_service_utils && cd ..
	#git rm portfolio/one_hundred_recs/ -rf
	#python portfolio/portfolio.py clean one_hundred_recs
	python portfolio/portfolio.py build one_hundred_recs --deploy 
	git add portfolio/one_hundred_recs/*.ipynb portfolio/one_hundred_recs/*.yml portfolio/one_hundred_recs/*.md 
	git add portfolio/sites/ 


build_test_100_recs:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/test_one_hundred_recs/ -rf
	python one_hundred_recs/deploy_portfolio_yaml.py   
	python portfolio/portfolio.py clean test_one_hundred_recs
	python portfolio/portfolio.py build test_one_hundred_recs --deploy 
	git add portfolio/test_one_hundred_recs/*.ipynb portfolio/test_one_hundred_recs/*.yml portfolio/test_one_hundred_recs/*.md 
	git add portfolio/sites/ 


build_dla_reports:
	#pip install -r portfolio/requirements.txt
	#cd dla/ && pip install -r requirements.txt && cd ..
	#git rm portfolio/dla/ -rf
	python portfolio/portfolio.py build dla --deploy 
	git add portfolio/dla/district_*/ portfolio/dla/*.yml portfolio/dla/*.md 
	git add portfolio/sites/dla.yml
    
build_quarterly_performance_metrics:
	pip install -r portfolio/requirements.txt
	cd bus_service_increase/ && make setup_bus_service_utils && cd ..
	git rm portfolio/quarterly_performance_metrics/ -rf
	python portfolio/portfolio.py clean quarterly_performance_metrics
	python portfolio/portfolio.py build quarterly_performance_metrics --deploy 
	git add portfolio/quarterly_performance_metrics/*.ipynb portfolio/quarterly_performance_metrics/*.yml portfolio/quarterly_performance_metrics/*.md 
	git add portfolio/sites/ 
    
build_hqta:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/hqta/ -rf
	python portfolio/portfolio.py clean hqta
	python portfolio/portfolio.py build hqta --deploy 
	git add portfolio/hqta/*.ipynb portfolio/hqta/*.yml portfolio/hqta/*.md 
	git add portfolio/sites/ 
    
build_segment_speeds:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/segment_speeds/ -rf
	python portfolio/portfolio.py clean segment_speeds
	python portfolio/portfolio.py build segment_speeds --deploy 
	git add portfolio/segment_speeds/*.ipynb portfolio/segment_speeds/*.yml portfolio/segment_speeds/*.md 
	git add portfolio/sites/ 
    
build_stop_segment_speeds:
	#pip install -r portfolio/requirements.txt
	#git rm portfolio/stop_segment_speeds/ -rf
	cd rt_segment_speeds && python deploy_portfolio_yaml.py && cd ../ 
	python portfolio/portfolio.py clean stop_segment_speeds
	python portfolio/portfolio.py build stop_segment_speeds --deploy 
	git add portfolio/stop_segment_speeds/*.ipynb portfolio/stop_segment_speeds/*.yml portfolio/stop_segment_speeds/*.md 
	git add portfolio/sites/     
    

add_precommit:
	pip install pre-commit
	pre-commit install 
	#pre-commit run --all-files 


# Add to _.bash_profile outside of data-analyses
#alias go='cd ~/data-analyses/portfolio && pip install -r requirements.txt && cd #../_shared_utils && make setup_env && cd ..'

install_env:
	cd ~/data-analyses/_shared_utils && make setup_env && cd ..
	#cd bus_service_increase/ && make setup_bus_service_utils && cd ..
	#cd rt_delay/ && make setup_rt_analysis && cd ..    
	#pip install -r portfolio/requirements.txt
	cd rt_segment_speeds && pip install -r requirements.txt && cd ..