import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load the dataset
df = pd.read_csv('All_Diets.csv')

# Handle missing data
df.fillna(df.mean(numeric_only=True), inplace=True)

# alculate average macronutrients per diet type
avg_macros = df.groupby('Diet_type')[['Protein(g)','Carbs(g)','Fat(g)']].mean()
print("Average Macros per Diet Type:\n", avg_macros)

# Top 5 protein-rich recipes per diet type
top_protein = df.sort_values('Protein(g)', ascending=False).groupby('Diet_type').head(5)
print("\nTop 5 Protein Recipes per Diet Type:\n", top_protein[['Diet_type','Recipe_name','Protein(g)']])

#Protein-to-Carbs and Carbs-to-Fat ratios
df['Protein_to_Carbs_ratio'] = df['Protein(g)'] / df['Carbs(g)']
df['Carbs_to_Fat_ratio'] = df['Carbs(g)'] / df['Fat(g)']

#Most common cuisine per diet type
most_common_cuisine = df.groupby('Diet_type')['Cuisine_type'].agg(lambda x: x.value_counts().index[0])
print("\nMost Common Cuisine per Diet Type:\n", most_common_cuisine)

# Visualizations

# Bar chart: Average protein
sns.barplot(x=avg_macros.index, y=avg_macros['Protein(g)'])
plt.title('Average Protein by Diet Type')
plt.ylabel('Protein (g)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('avg_protein.png')
plt.show()

# Bar chart: Average Carbs & Fat
avg_macros[['Carbs(g)','Fat(g)']].plot(kind='bar')
plt.title('Average Carbs & Fat by Diet Type')
plt.ylabel('Grams')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('avg_carbs_fat.png')
plt.show()

# Scatter plot: Top protein recipes
sns.scatterplot(data=top_protein, x='Recipe_name', y='Protein(g)', hue='Diet_type')
plt.xticks(rotation=90)
plt.title('Top 5 Protein Recipes per Diet Type')
plt.tight_layout()
plt.savefig('top_protein_scatter.png')
plt.show()

# Heatmap: Macronutrient correlations
sns.heatmap(df[['Protein(g)','Carbs(g)','Fat(g)']].corr(), annot=True)
plt.title('Macronutrient Correlation Heatmap')
plt.tight_layout()
plt.savefig('macro_heatmap.png')
plt.show()
