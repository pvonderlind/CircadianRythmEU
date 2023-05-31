# Circadian Rythm EU
This repsitory implements an interactive map of Europe which allows
users to explore effects of daytimes and workingtimes on the circadian rythm.

![Circadian Rythm Visualization](imgs/circ_vis_1.png)

We currently use Panel/Bokeh and Web Assembly to deploy our visualization on
GitHub Pages.

### Usage
You can run the visualization yourself using the `circadian_rythm_interactive.ipynb` notebook.
To use without dependency problems, it is recommended to use the Conda environment `environment.yml` as
kernel for your Jupyter server.

### Using Web Assembly
To convert the visalization to a self-contained web-page we use Web Assembly.
This is offered by the Panel library per default using Pyodide. Below is
the command to convert the `panel_app.py` to a html file and js file in the 
`docs` folder:

```bash
panel convert panel_app.py --to pyodide-worker --out docs
```

In order for GitHub Pages to be able to deploy the page, the
name of the html file needs to be changed to `index.html`
manually at the moment.